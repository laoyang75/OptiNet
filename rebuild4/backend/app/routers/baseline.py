"""API-08: 画像版本基线 — 当前 run vs 上一 run 的 final snapshot diff。"""
from fastapi import APIRouter, Query
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope
from ..core.context import base_context, CONTRACT_VERSION

router = APIRouter(prefix="/api", tags=["baseline"])


@router.get("/baseline/current")
def baseline_current():
    ctx = base_context()

    runs = fetchall("""
        SELECT profile_run_id, mode, status, snapshot_count,
               final_cell_count, final_bs_count, final_lac_count,
               params_hash, started_at, finished_at, is_current
        FROM rebuild4_meta.etl_profile_run_log
        WHERE status = 'completed'
        ORDER BY finished_at DESC LIMIT 2
    """)

    if not runs:
        return envelope({}, subject_scope="baseline",
                        subject_note="暂无已完成的画像运行",
                        context={"contract_version": CONTRACT_VERSION})

    current = runs[0]
    previous = runs[1] if len(runs) > 1 else None

    # 如果有两个 run，比较它们的 final snapshot
    diff_summary = None
    if previous:
        diff_summary = fetchone("""
            WITH cur AS (
                SELECT cell_id, lifecycle_state, anchorable, center_lon, center_lat, p90_radius_m
                FROM rebuild4_meta.etl_profile_snapshot_cell
                WHERE profile_run_id = %s AND snapshot_seq = %s
            ),
            prev AS (
                SELECT cell_id, lifecycle_state, anchorable, center_lon, center_lat, p90_radius_m
                FROM rebuild4_meta.etl_profile_snapshot_cell
                WHERE profile_run_id = %s AND snapshot_seq = %s
            )
            SELECT
                (SELECT COUNT(*) FROM cur) AS cur_total,
                (SELECT COUNT(*) FROM prev) AS prev_total,
                (SELECT COUNT(*) FROM cur WHERE cell_id NOT IN (SELECT cell_id FROM prev)) AS added,
                (SELECT COUNT(*) FROM prev WHERE cell_id NOT IN (SELECT cell_id FROM cur)) AS removed,
                (SELECT COUNT(*) FROM cur c JOIN prev p ON c.cell_id = p.cell_id
                 WHERE c.lifecycle_state != p.lifecycle_state) AS lifecycle_changed,
                (SELECT COUNT(*) FROM cur c JOIN prev p ON c.cell_id = p.cell_id
                 WHERE c.anchorable IS DISTINCT FROM p.anchorable) AS anchorable_changed
        """, (current["profile_run_id"], current["snapshot_count"],
              previous["profile_run_id"], previous["snapshot_count"]))

    return envelope({
        "current_run": current,
        "previous_run": previous,
        "diff_summary": diff_summary,
    }, subject_scope="baseline", context=ctx)


@router.get("/baseline/history")
def baseline_history(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    ctx = base_context()
    offset = (page - 1) * size

    rows = fetchall("""
        SELECT profile_run_id, mode, status, snapshot_count,
               final_cell_count, final_bs_count, final_lac_count,
               params_hash, source_date_from, source_date_to,
               started_at, finished_at, is_current
        FROM rebuild4_meta.etl_profile_run_log
        ORDER BY started_at DESC
        LIMIT %s OFFSET %s
    """, (size, offset))

    return envelope(rows, subject_scope="baseline", context=ctx)
