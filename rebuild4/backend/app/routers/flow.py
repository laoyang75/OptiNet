"""API-01: flow-overview, API-02: flow-snapshot — 改接 streaming snapshot。"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope, error_response
from ..core.context import base_context, get_current_profile_run, CONTRACT_VERSION

router = APIRouter(prefix="/api", tags=["flow"])


@router.get("/flow-overview")
def flow_overview():
    pr = get_current_profile_run()
    if not pr:
        return envelope({}, subject_scope="streaming",
                        subject_note="暂无 streaming 画像数据",
                        context={"contract_version": CONTRACT_VERSION})

    ctx = base_context()
    run_id = pr["profile_run_id"]
    latest_seq = pr["latest_seq"]

    # 当前 snapshot 指标
    current = fetchone("""
        SELECT snapshot_seq, snapshot_label, window_end_date,
               stream_cell_count, active_count, observing_count, waiting_count,
               anchorable_count, bs_count, lac_count
        FROM rebuild4_meta.etl_profile_snapshot
        WHERE profile_run_id = %s AND snapshot_seq = %s
    """, (run_id, latest_seq))

    # 与上一个 snapshot 的 diff 摘要
    diff_summary = None
    if latest_seq > 1:
        diff_summary = fetchone("""
            SELECT
                COUNT(*) FILTER (WHERE diff_kind = 'added')     AS added_cells,
                COUNT(*) FILTER (WHERE diff_kind = 'removed')   AS removed_cells,
                COUNT(*) FILTER (WHERE diff_kind = 'changed')   AS changed_cells,
                COUNT(*) FILTER (WHERE diff_kind = 'unchanged') AS unchanged_cells,
                COUNT(*) FILTER (WHERE to_lifecycle_state = 'active'
                    AND (from_lifecycle_state IS NULL OR from_lifecycle_state != 'active'))
                    AS new_active,
                COUNT(*) FILTER (WHERE anchorable_changed = true) AS anchorable_changed,
                COUNT(*) FILTER (WHERE centroid_shift_m > 500)   AS large_shift_cells
            FROM rebuild4_meta.etl_profile_snapshot_diff
            WHERE profile_run_id = %s AND from_seq = %s AND to_seq = %s
        """, (run_id, latest_seq - 1, latest_seq))

    # Cell 收敛曲线
    trend = fetchall("""
        SELECT snapshot_seq, snapshot_label, window_end_date,
               stream_cell_count, active_count, observing_count, waiting_count,
               anchorable_count
        FROM rebuild4_meta.etl_profile_snapshot
        WHERE profile_run_id = %s ORDER BY snapshot_seq
    """, (run_id,))

    # BS 收敛曲线
    bs_trend = fetchall("""
        SELECT snapshot_seq,
               COUNT(*) AS bs_total,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active') AS bs_active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS bs_observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') AS bs_waiting
        FROM rebuild4_meta.etl_profile_snapshot_bs
        WHERE profile_run_id = %s
        GROUP BY snapshot_seq ORDER BY snapshot_seq
    """, (run_id,))

    # LAC 收敛曲线
    lac_trend = fetchall("""
        SELECT snapshot_seq,
               COUNT(*) AS lac_total,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active') AS lac_active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS lac_observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') AS lac_waiting
        FROM rebuild4_meta.etl_profile_snapshot_lac
        WHERE profile_run_id = %s
        GROUP BY snapshot_seq ORDER BY snapshot_seq
    """, (run_id,))

    # BS/LAC diff 摘要（最新帧）
    bs_diff = None
    lac_diff = None
    if latest_seq > 1:
        bs_diff = fetchone("""
            SELECT
                COUNT(*) FILTER (WHERE diff_kind = 'added') AS added,
                COUNT(*) FILTER (WHERE diff_kind = 'changed') AS changed,
                COUNT(*) FILTER (WHERE to_lifecycle_state = 'active'
                    AND (from_lifecycle_state IS NULL OR from_lifecycle_state != 'active')) AS new_active
            FROM rebuild4_meta.etl_profile_snapshot_diff_bs
            WHERE profile_run_id = %s AND from_seq = %s AND to_seq = %s
        """, (run_id, latest_seq - 1, latest_seq))
        lac_diff = fetchone("""
            SELECT
                COUNT(*) FILTER (WHERE diff_kind = 'added') AS added,
                COUNT(*) FILTER (WHERE diff_kind = 'changed') AS changed,
                COUNT(*) FILTER (WHERE to_lifecycle_state = 'active'
                    AND (from_lifecycle_state IS NULL OR from_lifecycle_state != 'active')) AS new_active
            FROM rebuild4_meta.etl_profile_snapshot_diff_lac
            WHERE profile_run_id = %s AND from_seq = %s AND to_seq = %s
        """, (run_id, latest_seq - 1, latest_seq))

    # 当前生效的晋级规则（从 params 读取）
    rules = _load_lifecycle_rules()

    data = {
        "current_snapshot": current or {},
        "diff_summary": diff_summary or {},
        "bs_diff_summary": bs_diff or {},
        "lac_diff_summary": lac_diff or {},
        "trend": trend,
        "bs_trend": bs_trend,
        "lac_trend": lac_trend,
        "lifecycle_rules": rules,
    }
    return envelope(data, subject_scope="streaming", context=ctx)


def _load_lifecycle_rules() -> dict:
    """读取当前生效的晋级规则参数，供前端展示。"""
    import yaml
    from pathlib import Path
    params_path = Path(__file__).parent.parent / "etl" / "profile_params.yaml"
    try:
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return {
            "cell": {
                "active": params.get("lifecycle", {}).get("active", {}),
                "waiting_threshold": params.get("lifecycle", {}).get("waiting", {}),
                "anchorable": params.get("anchorable", {}),
            },
            "bs": params.get("bs_lifecycle", {}),
            "lac": params.get("lac_lifecycle", {}),
        }
    except Exception:
        return {}


@router.get("/flow-snapshot/timepoints")
def flow_snapshot_timepoints():
    pr = get_current_profile_run()
    if not pr:
        return envelope([], subject_scope="streaming",
                        subject_note="暂无可选快照时间点",
                        context={"contract_version": CONTRACT_VERSION})

    ctx = base_context()
    run_id = pr["profile_run_id"]

    timepoints = fetchall("""
        SELECT snapshot_seq, snapshot_label, window_end_date,
               stream_cell_count, active_count, anchorable_count, created_at
        FROM rebuild4_meta.etl_profile_snapshot
        WHERE profile_run_id = %s ORDER BY snapshot_seq
    """, (run_id,))

    return envelope(timepoints, subject_scope="streaming", context=ctx)


@router.get("/flow-snapshot")
def flow_snapshot(snapshot_seq: int = Query(...)):
    pr = get_current_profile_run()
    if not pr:
        return JSONResponse(status_code=404, content=error_response(
            "resource_not_found", "暂无 streaming 画像数据",
            "/api/flow-snapshot", CONTRACT_VERSION))

    ctx = base_context()
    run_id = pr["profile_run_id"]

    snap = fetchone("""
        SELECT snapshot_seq, snapshot_label, window_end_date,
               stream_cell_count, active_count, observing_count, waiting_count,
               anchorable_count, bs_count, lac_count, created_at
        FROM rebuild4_meta.etl_profile_snapshot
        WHERE profile_run_id = %s AND snapshot_seq = %s
    """, (run_id, snapshot_seq))

    if not snap:
        return JSONResponse(status_code=404, content=error_response(
            "resource_not_found", f"snapshot_seq={snapshot_seq} not found",
            "/api/flow-snapshot", CONTRACT_VERSION))

    # diff with previous
    diff_summary = None
    if snapshot_seq > 1:
        diff_summary = fetchone("""
            SELECT
                COUNT(*) FILTER (WHERE diff_kind = 'added')     AS added_cells,
                COUNT(*) FILTER (WHERE diff_kind = 'removed')   AS removed_cells,
                COUNT(*) FILTER (WHERE diff_kind = 'changed')   AS changed_cells,
                COUNT(*) FILTER (WHERE diff_kind = 'unchanged') AS unchanged_cells,
                COUNT(*) FILTER (WHERE to_lifecycle_state = 'active'
                    AND (from_lifecycle_state IS NULL OR from_lifecycle_state != 'active'))
                    AS new_active,
                COUNT(*) FILTER (WHERE anchorable_changed = true) AS anchorable_changed,
                COUNT(*) FILTER (WHERE centroid_shift_m > 500)   AS large_shift_cells
            FROM rebuild4_meta.etl_profile_snapshot_diff
            WHERE profile_run_id = %s AND from_seq = %s AND to_seq = %s
        """, (run_id, snapshot_seq - 1, snapshot_seq))

    data = {
        "snapshot": snap,
        "diff_summary": diff_summary or {},
    }
    return envelope(data, subject_scope="streaming", context=ctx)
