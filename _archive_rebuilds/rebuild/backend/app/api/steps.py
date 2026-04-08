"""Step registry and execution APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import StepOut
from app.services.cache import APP_CACHE
from app.services.workbench import (
    get_step_diff,
    get_step_metrics,
    get_step_object_diff,
    get_step_parameter_diff,
    get_step_rules,
    get_step_sql,
    get_step_samples,
)

router = APIRouter(prefix="/steps", tags=["steps"])


@router.get("", response_model=list[StepOut])
async def list_steps(
    layer: str | None = None,
    main_chain_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List all registered pipeline steps."""
    async def _builder():
        wheres, params = [], {}
        if layer:
            wheres.append("layer = :layer")
            params["layer"] = layer
        if main_chain_only:
            wheres.append("is_main_chain = true")
        where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

        result = await db.execute(text(f"""
            SELECT * FROM workbench.wb_step_registry {where_clause}
            ORDER BY step_order ASC
        """), params)
        return [StepOut(**r) for r in result.mappings().all()]

    data, _ = await APP_CACHE.get_or_set(
        f"steps:list:{layer}:{main_chain_only}",
        1800,
        _builder,
    )
    return data


@router.get("/{step_id}", response_model=StepOut)
async def get_step(step_id: str, db: AsyncSession = Depends(get_db)):
    async def _builder():
        result = await db.execute(
            text("SELECT * FROM workbench.wb_step_registry WHERE step_id = :id"),
            {"id": step_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(404, f"Step {step_id} not found")
        return StepOut(**row)

    data, _ = await APP_CACHE.get_or_set(f"steps:detail:{step_id}", 1800, _builder)
    return data


@router.get("/{step_id}/io-summary")
async def get_step_io_summary(step_id: str, db: AsyncSession = Depends(get_db)):
    """Get input/output table row counts for a step."""
    step = await db.execute(
        text("SELECT input_tables, output_tables FROM workbench.wb_step_registry WHERE step_id = :id"),
        {"id": step_id},
    )
    row = step.mappings().first()
    if not row:
        raise HTTPException(404, f"Step {step_id} not found")

    table_names = list(dict.fromkeys((row["input_tables"] or []) + (row["output_tables"] or [])))
    stats = await db.execute(
        text("""
            SELECT relname AS table_name, n_live_tup::bigint AS row_count
            FROM pg_stat_user_tables
            WHERE schemaname = 'pipeline' AND relname = ANY(:table_names)
        """),
        {"table_names": table_names},
    )
    stats_map = {item["table_name"]: item["row_count"] for item in stats.mappings().all()}

    tables_info = []
    for direction, table_list in [("input", row["input_tables"]), ("output", row["output_tables"])]:
        for tbl in table_list:
            tables_info.append({
                "direction": direction,
                "table_name": tbl,
                "row_count": int(stats_map[tbl]) if tbl in stats_map and stats_map[tbl] is not None else None,
            })
    return {"step_id": step_id, "tables": tables_info}


@router.get("/{step_id}/parameters")
async def get_step_parameters(
    step_id: str,
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取步骤参数，通过 run_id 绑定的 parameter_set_id 追溯，严禁读取 is_active。"""
    from app.services.workbench import latest_run_id

    resolved_run_id = run_id or await latest_run_id(db)
    if resolved_run_id is None:
        return {"step_id": step_id, "run_id": None, "parameter_set": None, "global": {}, "step": {}}

    # 通过 run_id -> parameter_set_id -> wb_parameter_set 追溯
    result = await db.execute(text("""
        SELECT ps.version_tag, ps.parameters
        FROM workbench.wb_run r
        JOIN workbench.wb_parameter_set ps ON ps.id = r.parameter_set_id
        WHERE r.run_id = :run_id
    """), {"run_id": resolved_run_id})
    row = result.mappings().first()
    if not row:
        return {"step_id": step_id, "run_id": resolved_run_id, "parameter_set": None, "global": {}, "step": {}}

    params = row["parameters"]
    step_key = step_id.replace("s", "step")
    step_params = params.get(step_key, {})
    global_params = params.get("global", {})

    return {
        "step_id": step_id,
        "run_id": resolved_run_id,
        "parameter_set": row["version_tag"],
        "global": global_params,
        "step": step_params,
    }


@router.get("/{step_id}/rules")
async def step_rules(
    step_id: str,
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_step_rules(db, step_id, run_id=run_id)


@router.get("/{step_id}/sql")
async def step_sql(
    step_id: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_step_sql(db, step_id, run_id=run_id, compare_run_id=compare_run_id)


@router.get("/{step_id}/metrics")
async def step_metrics(
    step_id: str,
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_step_metrics(db, step_id, run_id=run_id)


@router.get("/{step_id}/diff")
async def step_diff(
    step_id: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_step_diff(db, step_id, run_id=run_id, compare_run_id=compare_run_id)


@router.get("/{step_id}/parameter-diff")
async def step_parameter_diff(
    step_id: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_step_parameter_diff(db, step_id, run_id=run_id, compare_run_id=compare_run_id)


@router.get("/{step_id}/object-diff")
async def step_object_diff(
    step_id: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    return await get_step_object_diff(db, step_id, run_id=run_id, compare_run_id=compare_run_id, limit=limit)


@router.get("/{step_id}/samples")
async def step_samples(
    step_id: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await get_step_samples(db, step_id, run_id=run_id, compare_run_id=compare_run_id, limit=limit)
