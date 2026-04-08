#!/usr/bin/env python3
"""
Phase1 Visualization API Server (MVP)

Modes:
1) DB mode (preferred): set PHASE1_DB_DSN and read from Y_codex_obs_*.
2) Snapshot mode (fallback): read apps/phase1_ui/dashboard_data.json.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ModuleNotFoundError:  # local preview can run in snapshot mode without DB driver
    psycopg2 = None
    RealDictCursor = None
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
SNAPSHOT_FILE = Path(os.getenv("PHASE1_SNAPSHOT_FILE", str(ROOT_DIR / "apps/phase1_ui/dashboard_data.json")))
DEFAULT_DSN = os.getenv("PHASE1_DB_DSN", "").strip()
DEFAULT_DB_TIMEOUT_SEC = int(os.getenv("PHASE1_DB_TIMEOUT_SEC", "5"))
ISSUE_STORE_FILE = Path(os.getenv("PHASE1_ISSUE_STORE_FILE", str(ROOT_DIR / "apps/phase1_ui/issues_store.json")))
PATCH_STORE_FILE = Path(os.getenv("PHASE1_PATCH_STORE_FILE", str(ROOT_DIR / "apps/phase1_ui/patches_store.json")))
DEFAULT_PAGE_SIZE = int(os.getenv("PHASE1_PAGE_SIZE", "100"))
MAX_PAGE_SIZE = int(os.getenv("PHASE1_MAX_PAGE_SIZE", "500"))
ALLOWED_ISSUE_STATUS = {"new", "in_progress", "verified", "rejected", "rolled_back"}
ALLOWED_ISSUE_STATUS_TRANSITIONS = {
    "new": {"in_progress", "rejected", "rolled_back"},
    "in_progress": {"verified", "rejected", "rolled_back"},
    "verified": {"rolled_back"},
    "rejected": {"new", "in_progress"},
    "rolled_back": {"in_progress"},
}
ALLOWED_ISSUE_SEVERITY = {"P0", "P1", "P2"}


def _to_number(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float, bool)):
        return v
    try:
        s = str(v)
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        return v


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _error_code_from_status(status_code: int) -> str:
    if status_code == 400:
        return "BAD_REQUEST"
    if status_code == 401:
        return "UNAUTHORIZED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "HTTP_ERROR"


def _paginate_items(items: List[Dict[str, Any]], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int, int]:
    total = len(items)
    if total == 0:
        return [], 0, 0
    total_pages = ceil(total / page_size)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total, total_pages


def _issue_payload_validate(payload: Dict[str, Any], for_update: bool = False) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    allowed_keys = {"run_id", "severity", "layer_id", "title", "evidence_sql", "status", "owner"}
    unknown = [k for k in payload.keys() if k not in allowed_keys]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown issue fields: {', '.join(unknown)}")

    out: Dict[str, Any] = {}
    for k in allowed_keys:
        if k in payload:
            v = payload.get(k)
            out[k] = None if v is None else str(v).strip()

    if not for_update:
        if not out.get("severity"):
            raise HTTPException(status_code=400, detail="severity is required")
        if not out.get("layer_id"):
            raise HTTPException(status_code=400, detail="layer_id is required")
        if not out.get("title"):
            raise HTTPException(status_code=400, detail="title is required")

    if "severity" in out and out["severity"] and out["severity"] not in ALLOWED_ISSUE_SEVERITY:
        raise HTTPException(status_code=400, detail="severity must be one of P0/P1/P2")
    if "status" in out and out["status"] and out["status"] not in ALLOWED_ISSUE_STATUS:
        raise HTTPException(status_code=400, detail="status is invalid")
    return out


def _validate_issue_status_transition(current_status: str, next_status: str) -> None:
    curr = str(current_status or "").strip()
    nxt = str(next_status or "").strip()
    if not nxt or curr == nxt:
        return
    allowed = ALLOWED_ISSUE_STATUS_TRANSITIONS.get(curr, set())
    if nxt not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"invalid status transition: {curr} -> {nxt}",
        )


def _patch_payload_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    allowed_keys = {"issue_id", "run_id", "change_type", "change_summary", "owner", "verified_flag"}
    unknown = [k for k in payload.keys() if k not in allowed_keys]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown patch fields: {', '.join(unknown)}")

    out: Dict[str, Any] = {}
    if "issue_id" in payload and payload.get("issue_id") is not None:
        issue_id_raw = payload.get("issue_id")
        if str(issue_id_raw).strip().isdigit():
            out["issue_id"] = int(str(issue_id_raw).strip())
        else:
            raise HTTPException(status_code=400, detail="issue_id must be an integer")

    for k in ("run_id", "change_type", "change_summary", "owner"):
        if k in payload:
            v = payload.get(k)
            out[k] = None if v is None else str(v).strip()

    if "verified_flag" in payload:
        v = payload.get("verified_flag")
        if isinstance(v, bool):
            out["verified_flag"] = v
        elif isinstance(v, (int, float)):
            out["verified_flag"] = bool(v)
        else:
            s = str(v).strip().lower()
            if s in {"true", "1", "yes", "y"}:
                out["verified_flag"] = True
            elif s in {"false", "0", "no", "n", ""}:
                out["verified_flag"] = False
            else:
                raise HTTPException(status_code=400, detail="verified_flag must be boolean")

    if not out.get("change_type"):
        raise HTTPException(status_code=400, detail="change_type is required")
    if not out.get("change_summary"):
        raise HTTPException(status_code=400, detail="change_summary is required")
    out["verified_flag"] = bool(out.get("verified_flag", False))
    return out


class DataProvider:
    def __init__(self, dsn: str, snapshot_file: Path) -> None:
        self.dsn = dsn
        self.snapshot_file = snapshot_file

    @property
    def db_enabled(self) -> bool:
        return bool(self.dsn) and psycopg2 is not None

    @contextmanager
    def _conn(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed; DB mode unavailable")
        if not self.dsn:
            raise RuntimeError("PHASE1_DB_DSN is empty; DB mode unavailable")
        conn = psycopg2.connect(self.dsn, connect_timeout=DEFAULT_DB_TIMEOUT_SEC)
        conn.autocommit = True
        try:
            yield conn
        finally:
            conn.close()

    def _query(self, sql: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(params or ()))
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def load_snapshot(self) -> Dict[str, Any]:
        if not self.snapshot_file.exists():
            raise HTTPException(status_code=500, detail=f"snapshot file not found: {self.snapshot_file}")
        return json.loads(self.snapshot_file.read_text(encoding="utf-8"))

    def load_issue_store(self) -> List[Dict[str, Any]]:
        if not ISSUE_STORE_FILE.exists():
            return []
        text = ISSUE_STORE_FILE.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except Exception:
            return []
        if isinstance(raw, dict):
            items = raw.get("items", [])
            return items if isinstance(items, list) else []
        return raw if isinstance(raw, list) else []

    def save_issue_store(self, items: List[Dict[str, Any]]) -> None:
        ISSUE_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ISSUE_STORE_FILE.write_text(
            json.dumps({"items": items, "updated_at": _utc_now_iso()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_patch_store(self) -> List[Dict[str, Any]]:
        if not PATCH_STORE_FILE.exists():
            return []
        text = PATCH_STORE_FILE.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except Exception:
            return []
        if isinstance(raw, dict):
            items = raw.get("items", [])
            return items if isinstance(items, list) else []
        return raw if isinstance(raw, list) else []

    def save_patch_store(self, items: List[Dict[str, Any]]) -> None:
        PATCH_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PATCH_STORE_FILE.write_text(
            json.dumps({"items": items, "updated_at": _utc_now_iso()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def latest_run_id(self) -> str:
        rows = self._query(
            """
            SELECT run_id
            FROM public."Y_codex_obs_run_registry"
            ORDER BY run_started_at DESC
            LIMIT 1
            """
        )
        if not rows:
            raise HTTPException(status_code=404, detail="no run found in Y_codex_obs_run_registry")
        return str(rows[0]["run_id"])

    def resolve_run_id(self, run_id: Optional[str]) -> str:
        if run_id:
            return run_id
        if self.db_enabled:
            return self.latest_run_id()
        return str(self.load_snapshot().get("meta", {}).get("run_id", "snapshot"))

    def with_fallback(self, db_func, snapshot_func):
        if self.db_enabled:
            try:
                return db_func()
            except Exception:
                # fallback for local preview if DB is temporarily unavailable
                return snapshot_func()
        return snapshot_func()


provider = DataProvider(DEFAULT_DSN, SNAPSHOT_FILE)


app = FastAPI(title="Phase1 Visualization API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message", "http error"))
        details = detail.get("details", detail)
    else:
        message = str(detail)
        details = {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": _error_code_from_status(exc.status_code),
                "message": message,
                "details": details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "request validation failed",
                "details": {"errors": exc.errors()},
            }
        },
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "internal server error",
                "details": {"reason": str(exc)},
            }
        },
    )


def _overview_from_db(run_id: str) -> Dict[str, Any]:
    run_rows = provider._query(
        """
        SELECT run_id, run_status, run_started_at, run_finished_at
        FROM public."Y_codex_obs_run_registry"
        WHERE run_id = %s
        """,
        [run_id],
    )
    if not run_rows:
        raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")

    layers = provider._query(
        """
        SELECT layer_id, input_rows, output_rows, pass_flag, payload
        FROM public."Y_codex_obs_layer_snapshot"
        WHERE run_id = %s
        ORDER BY layer_id
        """,
        [run_id],
    )
    gate_sum = provider._query(
        """
        SELECT
          COUNT(*) FILTER (WHERE pass_flag IS TRUE) AS pass_cnt,
          COUNT(*) FILTER (WHERE pass_flag IS FALSE) AS fail_cnt,
          COUNT(*) AS total_cnt
        FROM public."Y_codex_obs_gate_result"
        WHERE run_id = %s
        """,
        [run_id],
    )[0]

    run = run_rows[0]
    return {
        "run_id": run["run_id"],
        "run_status": run["run_status"],
        "run_started_at": run["run_started_at"],
        "run_finished_at": run["run_finished_at"],
        "layers": [
            {
                "layer_id": r["layer_id"],
                "input_rows": _to_number(r["input_rows"]),
                "output_rows": _to_number(r["output_rows"]),
                "pass_flag": bool(r["pass_flag"]),
                "payload": r.get("payload") or {},
            }
            for r in layers
        ],
        "gate_summary": {
            "pass_cnt": _to_number(gate_sum["pass_cnt"]),
            "fail_cnt": _to_number(gate_sum["fail_cnt"]),
            "total_cnt": _to_number(gate_sum["total_cnt"]),
        },
    }


def _overview_from_snapshot(run_id: Optional[str]) -> Dict[str, Any]:
    s = provider.load_snapshot()
    layer_map = s.get("row_counts", {})
    gates = s.get("gate_results", [])
    rid = run_id or s.get("meta", {}).get("run_id")
    return {
        "run_id": rid,
        "run_status": "passed" if all(g.get("pass") for g in gates) else "failed",
        "run_started_at": s.get("meta", {}).get("snapshot_ts_utc"),
        "run_finished_at": s.get("meta", {}).get("snapshot_ts_utc"),
        "layers": [
            {"layer_id": "L0", "input_rows": None, "output_rows": layer_map.get("l0_rows"), "pass_flag": True, "payload": {}},
            {"layer_id": "L2", "input_rows": layer_map.get("l0_rows"), "output_rows": layer_map.get("l2_rows"), "pass_flag": True, "payload": {}},
            {"layer_id": "L3", "input_rows": layer_map.get("l2_rows"), "output_rows": layer_map.get("l3_bs_rows"), "pass_flag": True, "payload": {"object_level": "BS"}},
            {"layer_id": "L4_Final", "input_rows": layer_map.get("l2_rows"), "output_rows": layer_map.get("l4_final_rows"), "pass_flag": True, "payload": {}},
            {"layer_id": "L5_LAC", "input_rows": layer_map.get("l4_final_rows"), "output_rows": layer_map.get("l5_lac_rows"), "pass_flag": True, "payload": {}},
            {"layer_id": "L5_BS", "input_rows": layer_map.get("l4_final_rows"), "output_rows": layer_map.get("l5_bs_rows"), "pass_flag": True, "payload": {}},
            {"layer_id": "L5_CELL", "input_rows": layer_map.get("l4_final_rows"), "output_rows": layer_map.get("l5_cell_rows"), "pass_flag": True, "payload": {}},
        ],
        "gate_summary": {
            "pass_cnt": len([g for g in gates if g.get("pass")]),
            "fail_cnt": len([g for g in gates if not g.get("pass")]),
            "total_cnt": len(gates),
        },
    }


def _layer_from_db(
    run_id: str,
    layer_id: str,
    metric_like: Optional[str],
    rule_like: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    snap_rows = provider._query(
        """
        SELECT layer_id, input_rows, output_rows, pass_flag, payload
        FROM public."Y_codex_obs_layer_snapshot"
        WHERE run_id = %s AND layer_id = %s
        LIMIT 1
        """,
        [run_id, layer_id],
    )
    if not snap_rows:
        raise HTTPException(status_code=404, detail=f"layer_id not found: {layer_id}")
    qms = provider._query(
        """
        SELECT metric_code, metric_value, unit, payload
        FROM public."Y_codex_obs_quality_metric"
        WHERE run_id = %s AND layer_id = %s
        ORDER BY metric_code
        """,
        [run_id, layer_id],
    )
    rhs = provider._query(
        """
        SELECT rule_code, hit_rows, hit_ratio, payload
        FROM public."Y_codex_obs_rule_hit"
        WHERE run_id = %s AND layer_id = %s
        ORDER BY rule_code
        """,
        [run_id, layer_id],
    )
    s = snap_rows[0]
    quality_metrics = [
        {
            "metric_code": r["metric_code"],
            "metric_value": _to_number(r["metric_value"]),
            "unit": r["unit"],
            "payload": r.get("payload") or {},
        }
        for r in qms
    ]
    if metric_like:
        quality_metrics = [x for x in quality_metrics if metric_like in str(x["metric_code"])]

    rule_hits = [
        {
            "rule_code": r["rule_code"],
            "hit_rows": _to_number(r["hit_rows"]),
            "hit_ratio": _to_number(r["hit_ratio"]),
            "payload": r.get("payload") or {},
        }
        for r in rhs
    ]
    if rule_like:
        rule_hits = [x for x in rule_hits if rule_like in str(x["rule_code"])]

    qm_page, qm_total, qm_total_pages = _paginate_items(quality_metrics, page, page_size)
    rh_page, rh_total, rh_total_pages = _paginate_items(rule_hits, page, page_size)
    return {
        "run_id": run_id,
        "layer_id": layer_id,
        "snapshot": {
            "input_rows": _to_number(s["input_rows"]),
            "output_rows": _to_number(s["output_rows"]),
            "pass_flag": bool(s["pass_flag"]),
            "payload": s.get("payload") or {},
        },
        "quality_metrics": qm_page,
        "rule_hits": rh_page,
        "page": page,
        "page_size": page_size,
        "quality_metric_total": qm_total,
        "quality_metric_total_pages": qm_total_pages,
        "rule_hit_total": rh_total,
        "rule_hit_total_pages": rh_total_pages,
    }


def _layer_from_snapshot(
    run_id: Optional[str],
    layer_id: str,
    metric_like: Optional[str],
    rule_like: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    s = provider.load_snapshot()
    o = _overview_from_snapshot(run_id)
    snap = next((x for x in o["layers"] if x["layer_id"] == layer_id), None)
    if not snap:
        raise HTTPException(status_code=404, detail=f"layer_id not found: {layer_id}")

    metrics: List[Dict[str, Any]] = []
    if layer_id in ("L4", "L4_Step40", "L4_Final"):
        for k, v in s.get("gps_metrics", {}).items():
            metrics.append({"metric_code": k, "metric_value": _to_number(v), "unit": "rows", "payload": {}})
        for k, v in s.get("signal_metrics", {}).items():
            metrics.append(
                {
                    "metric_code": k,
                    "metric_value": _to_number(v),
                    "unit": "rows" if k.endswith("_cnt") else "fields",
                    "payload": {},
                }
            )
    if metric_like:
        metrics = [x for x in metrics if metric_like in str(x["metric_code"])]
    qm_page, qm_total, qm_total_pages = _paginate_items(metrics, page, page_size)
    return {
        "run_id": o["run_id"],
        "layer_id": layer_id,
        "snapshot": snap,
        "quality_metrics": qm_page,
        "rule_hits": [],
        "page": page,
        "page_size": page_size,
        "quality_metric_total": qm_total,
        "quality_metric_total_pages": qm_total_pages,
        "rule_hit_total": 0,
        "rule_hit_total_pages": 0,
    }


def _reconciliation_from_db(run_id: str, page: int, page_size: int) -> Dict[str, Any]:
    rows = provider._query(
        """
        SELECT check_code, lhs_value, rhs_value, diff_value, pass_flag, details
        FROM public."Y_codex_obs_reconciliation"
        WHERE run_id = %s
        ORDER BY check_code
        """,
        [run_id],
    )
    checks = [
        {
            "check_code": r["check_code"],
            "lhs_value": _to_number(r["lhs_value"]),
            "rhs_value": _to_number(r["rhs_value"]),
            "diff_value": _to_number(r["diff_value"]),
            "pass_flag": bool(r["pass_flag"]),
            "details": r.get("details") or {},
        }
        for r in rows
    ]
    page_items, total, total_pages = _paginate_items(checks, page, page_size)
    return {
        "run_id": run_id,
        "checks": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _reconciliation_from_snapshot(run_id: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
    s = provider.load_snapshot()
    rid = run_id or s.get("meta", {}).get("run_id")
    checks = [
        {
            "check_code": r.get("gate_code"),
            "check_name": r.get("gate_name"),
            "lhs_value": _to_number(r.get("actual_value")),
            "rhs_value": _to_number(r.get("expected_value")),
            "diff_value": _to_number(r.get("diff_value")),
            "pass_flag": bool(r.get("pass")),
            "details": {},
        }
        for r in s.get("gate_results", [])
    ]
    page_items, total, total_pages = _paginate_items(checks, page, page_size)
    return {
        "run_id": rid,
        "checks": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _exposure_from_db(run_id: str, object_level: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
    params: List[Any] = [run_id]
    where = 'WHERE run_id = %s'
    if object_level:
        where += " AND object_level = %s"
        params.append(object_level)
    rows = provider._query(
        f"""
        SELECT object_level, field_code, exposed_flag, true_obj_cnt, total_obj_cnt, note
        FROM public."Y_codex_obs_exposure_matrix"
        {where}
        ORDER BY object_level, field_code
        """,
        params,
    )
    data_rows = [
        {
            "object_level": r["object_level"],
            "field_code": r["field_code"],
            "exposed_flag": bool(r["exposed_flag"]),
            "true_obj_cnt": _to_number(r["true_obj_cnt"]),
            "total_obj_cnt": _to_number(r["total_obj_cnt"]),
            "note": r.get("note") or "",
        }
        for r in rows
    ]
    page_items, total, total_pages = _paginate_items(data_rows, page, page_size)
    return {"run_id": run_id, "rows": page_items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}


def _exposure_from_snapshot(run_id: Optional[str], object_level: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
    s = provider.load_snapshot()
    rid = run_id or s.get("meta", {}).get("run_id")
    bs_total = _to_number(s.get("row_counts", {}).get("l5_bs_rows")) or 0
    cell_total = _to_number(s.get("row_counts", {}).get("l5_cell_rows")) or 0
    bs = s.get("anomaly_counts", {}).get("bs", {})
    cell = s.get("anomaly_counts", {}).get("cell", {})
    rows = [
        {
            "object_level": "BS",
            "field_code": "is_bs_id_lt_256",
            "exposed_flag": True,
            "true_obj_cnt": _to_number(bs.get("bs_id_lt_256", 0)),
            "total_obj_cnt": bs_total,
            "note": "from Layer5_BS_Profile",
        },
        {
            "object_level": "BS",
            "field_code": "is_multi_operator_shared",
            "exposed_flag": True,
            "true_obj_cnt": _to_number(bs.get("multi_operator_shared", 0)),
            "total_obj_cnt": bs_total,
            "note": "from Layer5_BS_Profile",
        },
        {
            "object_level": "CELL",
            "field_code": "is_bs_id_lt_256",
            "exposed_flag": True,
            "true_obj_cnt": _to_number(cell.get("bs_id_lt_256", 0)),
            "total_obj_cnt": cell_total,
            "note": "from Layer5_Cell_Profile",
        },
        {
            "object_level": "CELL",
            "field_code": "is_multi_operator_shared",
            "exposed_flag": True,
            "true_obj_cnt": _to_number(cell.get("multi_operator_shared", 0)),
            "total_obj_cnt": cell_total,
            "note": "from Layer5_Cell_Profile",
        },
    ]
    if object_level:
        rows = [r for r in rows if r["object_level"] == object_level]
    page_items, total, total_pages = _paginate_items(rows, page, page_size)
    return {"run_id": rid, "rows": page_items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}


def _issues_from_db(
    run_id: Optional[str],
    status: Optional[str],
    severity: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    where = ["1=1"]
    params: List[Any] = []
    if run_id:
        where.append("run_id = %s")
        params.append(run_id)
    if status:
        where.append("status = %s")
        params.append(status)
    if severity:
        where.append("severity = %s")
        params.append(severity)

    total = _to_number(
        provider._query(
            f"""
            SELECT COUNT(*) AS cnt
            FROM public."Y_codex_obs_issue_log"
            WHERE {' AND '.join(where)}
            """,
            params,
        )[0]["cnt"]
    ) or 0
    offset = (page - 1) * page_size
    rows = provider._query(
        f"""
        SELECT issue_id, run_id, severity, layer_id, title, evidence_sql, status, owner, created_at, updated_at
        FROM public."Y_codex_obs_issue_log"
        WHERE {' AND '.join(where)}
        ORDER BY updated_at DESC, issue_id DESC
        LIMIT %s OFFSET %s
        """,
        [*params, page_size, offset],
    )
    total_pages = ceil(total / page_size) if total > 0 else 0
    return {
        "run_id": run_id,
        "items": rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _issues_from_snapshot(
    run_id: Optional[str],
    status: Optional[str],
    severity: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    s = provider.load_snapshot()
    rid = run_id or s.get("meta", {}).get("run_id")
    items = provider.load_issue_store()
    rows: List[Dict[str, Any]] = []
    for row in items:
        if run_id and str(row.get("run_id") or "") != str(run_id):
            continue
        if status and str(row.get("status") or "") != str(status):
            continue
        if severity and str(row.get("severity") or "") != str(severity):
            continue
        rows.append(row)
    rows.sort(key=lambda x: (x.get("updated_at") or "", x.get("issue_id") or 0), reverse=True)
    page_items, total, total_pages = _paginate_items(rows, page, page_size)
    return {"run_id": rid, "items": page_items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}


def _create_issue_db(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _issue_payload_validate(payload, for_update=False)
    status = p.get("status") or "new"
    rows = provider._query(
        """
        INSERT INTO public."Y_codex_obs_issue_log" (
          run_id, severity, layer_id, title, evidence_sql, status, owner
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING issue_id, run_id, severity, layer_id, title, evidence_sql, status, owner, created_at, updated_at
        """,
        [
            p.get("run_id"),
            p.get("severity"),
            p.get("layer_id"),
            p.get("title"),
            p.get("evidence_sql"),
            status,
            p.get("owner"),
        ],
    )
    return {"item": rows[0], "message": "issue created"}


def _create_issue_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _issue_payload_validate(payload, for_update=False)
    rows = provider.load_issue_store()
    next_id = 1 + max([_to_number(x.get("issue_id")) or 0 for x in rows], default=0)
    now = _utc_now_iso()
    item = {
        "issue_id": int(next_id),
        "run_id": p.get("run_id"),
        "severity": p.get("severity"),
        "layer_id": p.get("layer_id"),
        "title": p.get("title"),
        "evidence_sql": p.get("evidence_sql"),
        "status": p.get("status") or "new",
        "owner": p.get("owner"),
        "created_at": now,
        "updated_at": now,
    }
    rows.append(item)
    provider.save_issue_store(rows)
    return {"item": item, "message": "issue created (snapshot store)"}


def _update_issue_db(issue_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _issue_payload_validate(payload, for_update=True)
    if not p:
        raise HTTPException(status_code=400, detail="no updatable fields provided")
    current_rows = provider._query(
        """
        SELECT status
        FROM public."Y_codex_obs_issue_log"
        WHERE issue_id = %s
        LIMIT 1
        """,
        [issue_id],
    )
    if not current_rows:
        raise HTTPException(status_code=404, detail=f"issue_id not found: {issue_id}")
    if "status" in p and p.get("status"):
        _validate_issue_status_transition(str(current_rows[0].get("status") or ""), str(p["status"]))
    fields = []
    values: List[Any] = []
    for k in ("run_id", "severity", "layer_id", "title", "evidence_sql", "status", "owner"):
        if k in p:
            fields.append(f"{k} = %s")
            values.append(p[k])
    fields.append("updated_at = clock_timestamp()")
    rows = provider._query(
        f"""
        UPDATE public."Y_codex_obs_issue_log"
        SET {", ".join(fields)}
        WHERE issue_id = %s
        RETURNING issue_id, run_id, severity, layer_id, title, evidence_sql, status, owner, created_at, updated_at
        """,
        [*values, issue_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"issue_id not found: {issue_id}")
    return {"item": rows[0], "message": "issue updated"}


def _update_issue_snapshot(issue_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _issue_payload_validate(payload, for_update=True)
    if not p:
        raise HTTPException(status_code=400, detail="no updatable fields provided")
    rows = provider.load_issue_store()
    idx = next((i for i, row in enumerate(rows) if int(_to_number(row.get("issue_id")) or -1) == issue_id), -1)
    if idx < 0:
        raise HTTPException(status_code=404, detail=f"issue_id not found: {issue_id}")
    if "status" in p and p.get("status"):
        _validate_issue_status_transition(str(rows[idx].get("status") or ""), str(p["status"]))
    for k, v in p.items():
        rows[idx][k] = v
    rows[idx]["updated_at"] = _utc_now_iso()
    provider.save_issue_store(rows)
    return {"item": rows[idx], "message": "issue updated (snapshot store)"}


def _patches_from_db(
    run_id: Optional[str],
    issue_id: Optional[int],
    verified_flag: Optional[bool],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    where = ["1=1"]
    params: List[Any] = []
    if run_id:
        where.append("run_id = %s")
        params.append(run_id)
    if issue_id is not None:
        where.append("issue_id = %s")
        params.append(issue_id)
    if verified_flag is not None:
        where.append("verified_flag = %s")
        params.append(verified_flag)

    total = _to_number(
        provider._query(
            f"""
            SELECT COUNT(*) AS cnt
            FROM public."Y_codex_obs_patch_log"
            WHERE {' AND '.join(where)}
            """,
            params,
        )[0]["cnt"]
    ) or 0
    offset = (page - 1) * page_size
    rows = provider._query(
        f"""
        SELECT patch_id, issue_id, run_id, change_type, change_summary, owner, verified_flag, created_at
        FROM public."Y_codex_obs_patch_log"
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC, patch_id DESC
        LIMIT %s OFFSET %s
        """,
        [*params, page_size, offset],
    )
    total_pages = ceil(total / page_size) if total > 0 else 0
    return {
        "run_id": run_id,
        "items": rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _patches_from_snapshot(
    run_id: Optional[str],
    issue_id: Optional[int],
    verified_flag: Optional[bool],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    s = provider.load_snapshot()
    rid = run_id or s.get("meta", {}).get("run_id")
    items = provider.load_patch_store()
    rows: List[Dict[str, Any]] = []
    for row in items:
        if run_id and str(row.get("run_id") or "") != str(run_id):
            continue
        if issue_id is not None and int(_to_number(row.get("issue_id")) or -1) != int(issue_id):
            continue
        if verified_flag is not None and bool(row.get("verified_flag")) != bool(verified_flag):
            continue
        rows.append(row)
    rows.sort(key=lambda x: (x.get("created_at") or "", x.get("patch_id") or 0), reverse=True)
    page_items, total, total_pages = _paginate_items(rows, page, page_size)
    return {"run_id": rid, "items": page_items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}


def _create_patch_db(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _patch_payload_validate(payload)
    rows = provider._query(
        """
        INSERT INTO public."Y_codex_obs_patch_log" (
          issue_id, run_id, change_type, change_summary, owner, verified_flag
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING patch_id, issue_id, run_id, change_type, change_summary, owner, verified_flag, created_at
        """,
        [
            p.get("issue_id"),
            p.get("run_id"),
            p.get("change_type"),
            p.get("change_summary"),
            p.get("owner"),
            p.get("verified_flag", False),
        ],
    )
    return {"item": rows[0], "message": "patch log created"}


def _create_patch_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _patch_payload_validate(payload)
    rows = provider.load_patch_store()
    next_id = 1 + max([_to_number(x.get("patch_id")) or 0 for x in rows], default=0)
    now = _utc_now_iso()
    item = {
        "patch_id": int(next_id),
        "issue_id": p.get("issue_id"),
        "run_id": p.get("run_id"),
        "change_type": p.get("change_type"),
        "change_summary": p.get("change_summary"),
        "owner": p.get("owner"),
        "verified_flag": bool(p.get("verified_flag", False)),
        "created_at": now,
    }
    rows.append(item)
    provider.save_patch_store(rows)
    return {"item": item, "message": "patch log created (snapshot store)"}


TRACE_SELECT_SQL = """
SELECT
  seq_id,
  "记录id" AS record_id,
  cell_ts_std,
  ts_fill,
  operator_id_raw,
  tech_norm,
  lac_dec_final,
  bs_id_final,
  cell_id_dec,
  gps_status,
  gps_fix_strategy,
  gps_source,
  gps_status_final,
  lon_raw,
  lat_raw,
  lon_before_fix,
  lat_before_fix,
  bs_center_lon,
  bs_center_lat,
  lon_final,
  lat_final,
  gps_dist_to_bs_m,
  dist_threshold_m,
  is_collision_suspect,
  is_severe_collision,
  collision_reason,
  is_bs_id_lt_256,
  is_multi_operator_shared,
  shared_operator_cnt,
  shared_operator_list,
  is_dynamic_cell,
  dynamic_reason,
  half_major_dist_km,
  has_any_signal,
  signal_missing_before_cnt,
  signal_missing_after_cnt,
  signal_filled_field_cnt,
  signal_fill_source,
  signal_donor_seq_id,
  signal_donor_cell_id_dec,
  signal_donor_ts_fill,
  cell_donor_seq_id,
  sig_rsrp,
  sig_rsrq,
  sig_sinr,
  sig_rssi,
  sig_dbm,
  sig_asu_level,
  sig_level,
  sig_ss,
  sig_rsrp_final,
  sig_rsrq_final,
  sig_sinr_final,
  sig_rssi_final,
  sig_dbm_final,
  sig_asu_level_final,
  sig_level_final,
  sig_ss_final
FROM public."Y_codex_Layer4_Final_Cell_Library"
"""


def _normalize_row_values(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
            continue
        # keep datetimes JSON serializable in FastAPI (native handling), normalize decimals/strings
        out[k] = _to_number(v)
    return out


def _trace_from_db(run_id: str, trace_key: str) -> Dict[str, Any]:
    key = (trace_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="trace_key is required")

    match_type = "unknown"
    rows: List[Dict[str, Any]] = []

    seq_value: Optional[int] = None
    if key.isdigit():
        seq_value = int(key)
    elif key.lower().startswith("seq:") and key[4:].strip().isdigit():
        seq_value = int(key[4:].strip())

    if seq_value is not None:
        match_type = "seq_id"
        rows = provider._query(
            TRACE_SELECT_SQL + " WHERE seq_id = %s ORDER BY ts_fill DESC LIMIT 20",
            [seq_value],
        )
    else:
        rows = provider._query(
            TRACE_SELECT_SQL + ' WHERE "记录id" = %s ORDER BY ts_fill DESC LIMIT 20',
            [key],
        )
        if rows:
            match_type = "record_id"
        else:
            rows = provider._query(
                TRACE_SELECT_SQL + " WHERE did = %s ORDER BY ts_fill DESC LIMIT 20",
                [key],
            )
            if rows:
                match_type = "did"

    if not rows:
        raise HTTPException(status_code=404, detail=f"trace not found: {trace_key}")

    norm_rows = [_normalize_row_values(r) for r in rows]
    return {
        "run_id": run_id,
        "trace_key": trace_key,
        "match_type": match_type,
        "match_count": len(norm_rows),
        "primary": norm_rows[0],
        "rows": norm_rows,
        "message": "命中多条记录，已按最新时间优先展示" if len(norm_rows) > 1 else "ok",
    }


def _trace_from_snapshot(run_id: Optional[str], trace_key: str) -> Dict[str, Any]:
    s = provider.load_snapshot()
    rid = run_id or s.get("meta", {}).get("run_id")
    return {
        "run_id": rid,
        "trace_key": trace_key,
        "match_type": "snapshot_only",
        "match_count": 0,
        "primary": None,
        "rows": [],
        "message": "当前为快照模式（snapshot），不提供行级 Trace 明细。请配置 PHASE1_DB_DSN 后重试。",
    }


def _dashboard_snapshot_from_db(run_id: str) -> Dict[str, Any]:
    ov = _overview_from_db(run_id)
    rc = {x["layer_id"]: x for x in ov["layers"]}
    q = provider._query(
        """
        SELECT metric_code, metric_value
        FROM public."Y_codex_obs_quality_metric"
        WHERE run_id = %s AND layer_id = 'L4'
        """,
        [run_id],
    )
    qm = {r["metric_code"]: _to_number(r["metric_value"]) for r in q}
    an = provider._query(
        """
        SELECT object_level, anomaly_code, obj_cnt
        FROM public."Y_codex_obs_anomaly_stats"
        WHERE run_id = %s
        ORDER BY object_level, anomaly_code
        """,
        [run_id],
    )
    bs: Dict[str, Any] = {}
    cell: Dict[str, Any] = {}
    for r in an:
        if r["object_level"] == "BS":
            bs[r["anomaly_code"]] = _to_number(r["obj_cnt"])
        else:
            cell[r["anomaly_code"]] = _to_number(r["obj_cnt"])
    gates = provider._query(
        """
        SELECT gate_code, gate_name, actual_value, expected_value, diff_value, pass_flag
        FROM public."Y_codex_obs_gate_result"
        WHERE run_id = %s
        ORDER BY gate_code
        """,
        [run_id],
    )
    gate_results = [
        {
            "gate_code": g["gate_code"],
            "gate_name": g["gate_name"],
            "actual_value": _to_number(g["actual_value"]),
            "expected_value": _to_number(g["expected_value"]),
            "diff_value": _to_number(g["diff_value"]),
            "pass": bool(g["pass_flag"]),
        }
        for g in gates
    ]
    return {
        "meta": {
            "project": "Phase1 可视化研究平台",
            "db_name": os.getenv("PHASE1_DB_NAME", "unknown"),
            "snapshot_ts_utc": ov["run_started_at"],
            "run_id": run_id,
            "status": "s0_completed",
        },
        "row_counts": {
            "l0_rows": _to_number(rc.get("L0", {}).get("output_rows")),
            "l2_rows": _to_number(rc.get("L2", {}).get("output_rows")),
            "l3_bs_rows": _to_number(rc.get("L3", {}).get("output_rows")),
            "l4_final_rows": _to_number(rc.get("L4_Final", {}).get("output_rows")),
            "l5_lac_rows": _to_number(rc.get("L5_LAC", {}).get("output_rows")),
            "l5_bs_rows": _to_number(rc.get("L5_BS", {}).get("output_rows")),
            "l5_cell_rows": _to_number(rc.get("L5_CELL", {}).get("output_rows")),
        },
        "gps_metrics": {
            "row_cnt": qm.get("row_cnt"),
            "gps_missing_cnt": qm.get("gps_missing_cnt"),
            "gps_drift_cnt": qm.get("gps_drift_cnt"),
            "gps_fill_from_bs_cnt": qm.get("gps_fill_from_bs_cnt"),
            "gps_fill_from_bs_severe_collision_cnt": qm.get("gps_fill_from_bs_severe_collision_cnt"),
            "gps_fill_from_risk_bs_cnt": qm.get("gps_fill_from_risk_bs_cnt"),
            "gps_not_filled_cnt": qm.get("gps_not_filled_cnt"),
            "severe_collision_row_cnt": qm.get("severe_collision_row_cnt"),
            "bs_id_lt_256_row_cnt": qm.get("bs_id_lt_256_row_cnt"),
        },
        "signal_metrics": {
            "need_fill_row_cnt": qm.get("need_fill_row_cnt"),
            "filled_by_cell_nearest_row_cnt": qm.get("filled_by_cell_nearest_row_cnt"),
            "filled_by_bs_top_cell_row_cnt": qm.get("filled_by_bs_top_cell_row_cnt"),
            "missing_field_before_sum": qm.get("missing_field_before_sum"),
            "missing_field_after_sum": qm.get("missing_field_after_sum"),
            "filled_field_sum": qm.get("filled_field_sum"),
        },
        "anomaly_counts": {"bs": bs, "cell": cell},
        "exposure_contract": {"cn_contract_cols": 8, "en_contract_cols": 8},
        "gate_results": gate_results,
        "closure_note": {
            "dynamic_all_scope_l4": None,
            "dynamic_filtered_scope_l4": cell.get("dynamic_cell"),
            "dynamic_l5": cell.get("dynamic_cell"),
            "explain": "DB snapshot mode: dynamic filtered scope aligned with Layer5 output.",
        },
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    db_ok = False
    db_err = ""
    if provider.db_enabled:
        try:
            provider._query("SELECT 1 AS ok")
            db_ok = True
        except Exception as exc:  # pragma: no cover - runtime only
            db_err = str(exc)
    return {
        "service": "phase1_api",
        "db_mode_configured": provider.db_enabled,
        "db_mode_active": db_ok,
        "db_error": db_err,
        "snapshot_file": str(SNAPSHOT_FILE),
    }


@app.get("/api/phase1/overview")
def get_overview(
    run_id: Optional[str] = Query(default=None),
    operator: Optional[str] = Query(default=None),
    tech: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    resolved = provider.resolve_run_id(run_id)
    data = provider.with_fallback(lambda: _overview_from_db(resolved), lambda: _overview_from_snapshot(resolved))
    data["filters"] = {"operator": operator, "tech": tech, "tag": tag}
    return data


@app.get("/api/phase1/layer/{layer_id}")
def get_layer(
    layer_id: str,
    run_id: Optional[str] = Query(default=None),
    metric_like: Optional[str] = Query(default=None),
    rule_like: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    operator: Optional[str] = Query(default=None),
    tech: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    resolved = provider.resolve_run_id(run_id)
    data = provider.with_fallback(
        lambda: _layer_from_db(resolved, layer_id, metric_like, rule_like, page, page_size),
        lambda: _layer_from_snapshot(resolved, layer_id, metric_like, rule_like, page, page_size),
    )
    data["filters"] = {"operator": operator, "tech": tech, "tag": tag}
    return data


@app.get("/api/phase1/reconciliation")
def get_reconciliation(
    run_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    operator: Optional[str] = Query(default=None),
    tech: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    resolved = provider.resolve_run_id(run_id)
    data = provider.with_fallback(
        lambda: _reconciliation_from_db(resolved, page, page_size),
        lambda: _reconciliation_from_snapshot(resolved, page, page_size),
    )
    data["filters"] = {"operator": operator, "tech": tech, "tag": tag}
    return data


@app.get("/api/phase1/exposure-matrix")
def get_exposure_matrix(
    run_id: Optional[str] = Query(default=None),
    object_level: Optional[str] = Query(default=None, pattern="^(BS|CELL)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    operator: Optional[str] = Query(default=None),
    tech: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    resolved = provider.resolve_run_id(run_id)
    data = provider.with_fallback(
        lambda: _exposure_from_db(resolved, object_level, page, page_size),
        lambda: _exposure_from_snapshot(resolved, object_level, page, page_size),
    )
    data["filters"] = {"operator": operator, "tech": tech, "tag": tag}
    return data


@app.get("/api/phase1/issues")
def get_issues(
    run_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, pattern="^(new|in_progress|verified|rejected|rolled_back)$"),
    severity: Optional[str] = Query(default=None, pattern="^(P0|P1|P2)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> Dict[str, Any]:
    return provider.with_fallback(
        lambda: _issues_from_db(run_id, status, severity, page, page_size),
        lambda: _issues_from_snapshot(run_id, status, severity, page, page_size),
    )


@app.post("/api/phase1/issues")
def create_issue(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return provider.with_fallback(
        lambda: _create_issue_db(payload),
        lambda: _create_issue_snapshot(payload),
    )


@app.patch("/api/phase1/issues/{issue_id}")
def update_issue(issue_id: int, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return provider.with_fallback(
        lambda: _update_issue_db(issue_id, payload),
        lambda: _update_issue_snapshot(issue_id, payload),
    )


@app.get("/api/phase1/patches")
def get_patches(
    run_id: Optional[str] = Query(default=None),
    issue_id: Optional[int] = Query(default=None, ge=1),
    verified_flag: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> Dict[str, Any]:
    return provider.with_fallback(
        lambda: _patches_from_db(run_id, issue_id, verified_flag, page, page_size),
        lambda: _patches_from_snapshot(run_id, issue_id, verified_flag, page, page_size),
    )


@app.post("/api/phase1/patches")
def create_patch(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return provider.with_fallback(
        lambda: _create_patch_db(payload),
        lambda: _create_patch_snapshot(payload),
    )


@app.get("/api/phase1/trace/{trace_key}")
def get_trace(trace_key: str, run_id: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    resolved = provider.resolve_run_id(run_id)
    return provider.with_fallback(lambda: _trace_from_db(resolved, trace_key), lambda: _trace_from_snapshot(resolved, trace_key))


@app.get("/api/phase1/dashboard-snapshot")
def get_dashboard_snapshot(run_id: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    resolved = provider.resolve_run_id(run_id)
    return provider.with_fallback(lambda: _dashboard_snapshot_from_db(resolved), provider.load_snapshot)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("PHASE1_API_HOST", "127.0.0.1")
    port = int(os.getenv("PHASE1_API_PORT", "8508"))
    uvicorn.run(app, host=host, port=port, log_level="info")
