"""API-06: observation-workspace, API-07: anomaly-workspace."""
from fastapi import APIRouter, Query, Path
from fastapi.responses import JSONResponse
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope, error_response
from ..core.context import base_context, get_current_pointer, get_current_profile_run, CONTRACT_VERSION

router = APIRouter(prefix="/api", tags=["workspaces"])


@router.get("/observation-workspace")
def observation_workspace(
    lifecycle: str = Query(None),
    sort: str = Query("anchorable_desc"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    pr = get_current_profile_run()
    if not pr:
        return envelope([], subject_scope="streaming",
                        subject_note="当前没有等待或观察中的对象",
                        context={"contract_version": CONTRACT_VERSION})

    ctx = base_context()
    if lifecycle:
        ctx["filter_lifecycle"] = lifecycle
    ctx["sort_key"] = sort

    # 从当前画像表中查 waiting/observing Cell
    conditions = ["c.lifecycle_state IN ('waiting', 'observing')"]
    params: list = []

    if lifecycle:
        conditions.append("c.lifecycle_state = %s")
        params.append(lifecycle)

    order = {
        "anchorable_desc": "c.anchorable DESC, c.independent_obs DESC",
        "obs_desc": "c.independent_obs DESC",
        "active_days_desc": "c.active_days DESC",
    }.get(sort, "c.anchorable DESC, c.independent_obs DESC")

    where = " AND ".join(conditions)
    offset = (page - 1) * size

    rows = fetchall(f"""
        SELECT c.cell_id, c.bs_id, c.lac, c.lifecycle_state, c.anchorable,
               c.independent_obs, c.independent_days, c.active_days,
               c.distinct_dev_id, c.center_lon, c.center_lat,
               c.p50_radius_m, c.p90_radius_m, c.position_grade,
               c.drift_pattern, c.observed_span_hours,
               c.gps_confidence, c.signal_confidence
        FROM rebuild4.etl_dim_cell c
        WHERE {where}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """, (*params, size, offset))

    total = fetchone(f"""
        SELECT COUNT(*) as cnt FROM rebuild4.etl_dim_cell c WHERE {where}
    """, params)

    # 汇总
    summary = fetchone("""
        SELECT
            COUNT(*) FILTER (WHERE lifecycle_state = 'waiting')   AS waiting,
            COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS observing,
            COUNT(*) FILTER (WHERE lifecycle_state = 'active')    AS active,
            COUNT(*) FILTER (WHERE anchorable)                    AS anchorable
        FROM rebuild4.etl_dim_cell
    """)

    # 最近一次 diff 中的观察信号
    run_id = pr["profile_run_id"]
    latest_seq = pr["latest_seq"]
    observation_signals = {}
    if latest_seq > 1:
        observation_signals = fetchone("""
            SELECT
                COUNT(*) FILTER (WHERE diff_kind = 'added'
                    AND to_lifecycle_state = 'observing') AS new_observing,
                COUNT(*) FILTER (WHERE diff_kind = 'changed'
                    AND to_lifecycle_state = 'active')    AS promoted_to_active,
                COUNT(*) FILTER (WHERE centroid_shift_m > 500
                    AND to_lifecycle_state IN ('waiting', 'observing'))
                    AS large_shift_cells,
                COUNT(*) FILTER (WHERE anchorable_changed = true) AS anchorable_changed
            FROM rebuild4_meta.etl_profile_snapshot_diff
            WHERE profile_run_id = %s AND from_seq = %s AND to_seq = %s
        """, (run_id, latest_seq - 1, latest_seq)) or {}

    return envelope({
        "items": rows,
        "summary": summary or {},
        "observation_signals": observation_signals,
        "total": total["cnt"] if total else 0,
        "page": page,
        "size": size,
    }, subject_scope="streaming",
       subject_note="当前没有等待或观察中的对象" if not rows else None,
       context=ctx)


@router.get("/anomaly-workspace/summary")
def anomaly_summary(view: str = Query("all")):
    cp = get_current_pointer()
    if not cp:
        return envelope({}, subject_scope="batch", subject_note="当前没有异常数据",
                        context={"contract_version": CONTRACT_VERSION})

    ctx = base_context()
    ctx["view_mode"] = view
    batch_id = cp["current_batch_id"]

    obj_summary = fetchone("""
        SELECT
            COUNT(*) as object_total,
            COUNT(*) FILTER (WHERE forbid_anchor = true) as anchor_blocked,
            COUNT(*) FILTER (WHERE forbid_baseline = true) as baseline_blocked
        FROM rebuild4_meta.batch_anomaly_object_summary WHERE batch_id = %s
    """, (batch_id,))

    rec_summary = fetchone("""
        SELECT
            COUNT(*) as record_types,
            COALESCE(SUM(affected_rows), 0) as record_total
        FROM rebuild4_meta.batch_anomaly_record_summary WHERE batch_id = %s
    """, (batch_id,))

    rejected = fetchone("""
        SELECT COUNT(*) as cnt FROM rebuild4.fact_rejected
        WHERE batch_id = %s
    """, (batch_id,))

    return envelope({
        "object_total": int(obj_summary["object_total"]) if obj_summary else 0,
        "record_total": int(rec_summary["record_total"]) if rec_summary else 0,
        "anchor_blocked": int(obj_summary["anchor_blocked"]) if obj_summary else 0,
        "baseline_blocked": int(obj_summary["baseline_blocked"]) if obj_summary else 0,
        "rejected": int(rejected["cnt"]) if rejected else 0,
    }, subject_scope="batch", context=ctx)


@router.get("/anomaly-workspace")
def anomaly_workspace(
    view: str = Query("object"),
    type: str = Query(None),
    severity: str = Query(None),
    trend: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    cp = get_current_pointer()
    if not cp:
        return envelope([], subject_scope="batch", subject_note="当前没有对象级异常",
                        context={"contract_version": CONTRACT_VERSION})

    ctx = base_context()
    ctx["view_mode"] = view
    if type:
        ctx["filter_type"] = type
    if severity:
        ctx["filter_severity"] = severity
    batch_id = cp["current_batch_id"]
    offset = (page - 1) * size

    if view == "record":
        conditions = ["r.batch_id = %s"]
        params: list = [batch_id]
        if type:
            conditions.append("r.anomaly_type = %s")
            params.append(type)
        where = " AND ".join(conditions)
        rows = fetchall(f"""
            SELECT r.* FROM rebuild4_meta.batch_anomaly_record_summary r
            WHERE {where} ORDER BY r.affected_rows DESC
            LIMIT %s OFFSET %s
        """, (*params, size, offset))
        total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4_meta.batch_anomaly_record_summary r WHERE {where}", params)
    else:
        conditions = ["a.batch_id = %s"]
        params = [batch_id]
        if type:
            conditions.append("a.anomaly_type = %s")
            params.append(type)
        if severity:
            conditions.append("a.severity = %s")
            params.append(severity)
        if trend:
            conditions.append("a.evidence_trend = %s")
            params.append(trend)
        where = " AND ".join(conditions)
        rows = fetchall(f"""
            SELECT a.* FROM rebuild4_meta.batch_anomaly_object_summary a
            WHERE {where} ORDER BY a.severity, a.anomaly_type
            LIMIT %s OFFSET %s
        """, (*params, size, offset))
        total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4_meta.batch_anomaly_object_summary a WHERE {where}", params)

    return envelope(rows, subject_scope="batch",
                    subject_note="当前没有对象级异常" if view == "object" and not rows else
                                "当前没有记录级异常" if view == "record" and not rows else None,
                    context={**ctx, "total": total["cnt"] if total else 0, "page": page, "size": size})


@router.get("/anomaly-workspace/{key}/impact")
def anomaly_impact(key: str = Path(...)):
    cp = get_current_pointer()
    if not cp:
        return JSONResponse(status_code=404, content=error_response(
            "object_not_found", f"object_key={key} not found",
            f"/api/anomaly-workspace/{key}/impact", CONTRACT_VERSION))

    batch_id = cp["current_batch_id"]
    impacts = fetchall("""
        SELECT * FROM rebuild4_meta.batch_anomaly_impact_summary
        WHERE batch_id = %s AND object_key = %s
        ORDER BY impact_count DESC
    """, (batch_id, key))

    if not impacts:
        # check if object exists
        obj = fetchone("""
            SELECT object_key FROM rebuild4_meta.batch_anomaly_object_summary
            WHERE object_key = %s LIMIT 1
        """, (key,))
        if not obj:
            return JSONResponse(status_code=404, content=error_response(
                "object_not_found", f"object_key={key} not found",
                f"/api/anomaly-workspace/{key}/impact", CONTRACT_VERSION))

    ctx = base_context()
    return envelope(impacts, subject_scope="batch", context=ctx)
