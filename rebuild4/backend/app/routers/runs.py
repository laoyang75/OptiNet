"""API-03: 画像运行中心 — 改接 etl_profile_run_log + snapshot。"""
from fastapi import APIRouter, Query, Path
from fastapi.responses import JSONResponse
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope, error_response
from ..core.context import base_context, CONTRACT_VERSION

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs/current")
def runs_current():
    ctx = base_context()

    current = fetchone("""
        SELECT * FROM rebuild4_meta.etl_profile_run_log
        WHERE is_current = true LIMIT 1
    """)

    runs = fetchall("""
        SELECT profile_run_id, mode, status, snapshot_count,
               final_cell_count, final_bs_count, final_lac_count,
               params_hash, source_date_from, source_date_to,
               started_at, finished_at, is_current
        FROM rebuild4_meta.etl_profile_run_log
        ORDER BY started_at DESC
    """)

    return envelope({
        "current_run": current,
        "runs": runs,
    }, subject_scope="profile_run", context=ctx)


@router.get("/runs/{run_id}/snapshots")
def run_snapshots(run_id: str = Path(...)):
    ctx = base_context()

    run = fetchone("""
        SELECT * FROM rebuild4_meta.etl_profile_run_log
        WHERE profile_run_id = %s
    """, (run_id,))

    if not run:
        return JSONResponse(status_code=404, content=error_response(
            "resource_not_found", f"profile_run_id={run_id} not found",
            f"/api/runs/{run_id}/snapshots", CONTRACT_VERSION))

    snapshots = fetchall("""
        SELECT snapshot_seq, snapshot_label, window_end_date,
               stream_cell_count, active_count, observing_count, waiting_count,
               anchorable_count, bs_count, lac_count, created_at
        FROM rebuild4_meta.etl_profile_snapshot
        WHERE profile_run_id = %s ORDER BY snapshot_seq
    """, (run_id,))

    return envelope({
        "run": run,
        "snapshots": snapshots,
    }, subject_scope="profile_run", context=ctx)
