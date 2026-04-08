"""API-04: objects, API-05: objects/:key/detail — 改接 etl_dim_*。"""
from fastapi import APIRouter, Query, Path
from fastapi.responses import JSONResponse
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope, error_response
from ..core.context import base_context, get_current_profile_run, CONTRACT_VERSION

router = APIRouter(prefix="/api", tags=["objects"])


def _dim_table(object_type: str) -> str:
    return {"cell": "etl_dim_cell", "bs": "etl_dim_bs", "lac": "etl_dim_lac"}.get(object_type, "etl_dim_cell")


def _pk(object_type: str) -> str:
    return {"cell": "cell_id", "bs": "bs_id", "lac": "lac"}.get(object_type, "cell_id")


@router.get("/objects")
def objects_list(
    type: str = Query("cell"),
    lifecycle: str = Query(None),
    anchorable: str = Query(None),
    position_grade: str = Query(None),
    drift_pattern: str = Query(None),
    cell_scale: str = Query(None),
    q: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    ctx = base_context()
    ctx["object_type"] = type

    tbl = _dim_table(type)
    pk = _pk(type)
    conditions = ["1=1"]
    params: list = []

    if lifecycle:
        conditions.append("o.lifecycle_state = %s")
        params.append(lifecycle)
    if anchorable == "true":
        conditions.append("o.anchorable = true")
    elif anchorable == "false":
        conditions.append("o.anchorable = false")
    if position_grade:
        conditions.append("o.position_grade = %s")
        params.append(position_grade)
    if drift_pattern:
        conditions.append("o.drift_pattern = %s")
        params.append(drift_pattern)
    if cell_scale and type == "cell":
        conditions.append("o.cell_scale = %s")
        params.append(cell_scale)
    if q:
        conditions.append(f"o.{pk} ILIKE %s")
        params.append(f"%{q}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * size

    rows = fetchall(f"""
        SELECT o.*
        FROM rebuild4.{tbl} o
        WHERE {where}
        ORDER BY o.{pk}
        LIMIT %s OFFSET %s
    """, (*params, size, offset))

    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4.{tbl} o WHERE {where}", params)

    return envelope(rows, subject_scope="object", subject_note="暂无对象" if not rows else None,
                    context={**ctx, "total": total["cnt"] if total else 0, "page": page, "size": size})


@router.get("/objects/summary")
def objects_summary(type: str = Query("cell")):
    ctx = base_context()
    ctx["object_type"] = type
    tbl = _dim_table(type)

    summary = fetchone(f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE lifecycle_state = 'active') as active,
            COUNT(*) FILTER (WHERE lifecycle_state = 'observing') as observing,
            COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') as waiting,
            COUNT(*) FILTER (WHERE anchorable = true) as anchorable,
            COUNT(*) FILTER (WHERE position_grade IN ('excellent', 'good')) as good_position
        FROM rebuild4.{tbl}
    """)
    return envelope(summary or {}, subject_scope="object", context=ctx)


@router.get("/objects/{key}/detail")
def object_detail(key: str = Path(...)):
    obj = None
    obj_type = None
    for otype, tbl, pk in [("cell", "etl_dim_cell", "cell_id"),
                            ("bs", "etl_dim_bs", "bs_id"),
                            ("lac", "etl_dim_lac", "lac")]:
        obj = fetchone(f"SELECT * FROM rebuild4.{tbl} WHERE {pk} = %s", (key,))
        if obj:
            obj_type = otype
            break

    if not obj:
        return JSONResponse(status_code=404, content=error_response(
            "object_not_found", f"key={key} not found",
            f"/api/objects/{key}/detail", CONTRACT_VERSION))

    ctx = base_context()
    ctx["object_key"] = key

    # 最近一次 snapshot diff 中此 Cell 的变化
    pr = get_current_profile_run()
    latest_diff = None
    if pr and obj_type == "cell" and pr["latest_seq"] > 1:
        latest_diff = fetchone("""
            SELECT diff_kind, from_lifecycle_state, to_lifecycle_state,
                   centroid_shift_m, p90_delta_m, anchorable_changed
            FROM rebuild4_meta.etl_profile_snapshot_diff
            WHERE profile_run_id = %s AND from_seq = %s AND to_seq = %s AND cell_id = %s
        """, (pr["profile_run_id"], pr["latest_seq"] - 1, pr["latest_seq"], key))

    return envelope({
        "object": obj,
        "object_type": obj_type,
        "latest_diff": latest_diff,
        "state_history_note": "历史状态追溯功能已冻结，待 streaming 模块稳定后由 snapshot diff 替代",
    }, subject_scope="object", context=ctx)
