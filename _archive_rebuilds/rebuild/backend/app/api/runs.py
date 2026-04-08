"""Run management APIs: create, list, get, update status."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import RunCreate, RunOut, PaginatedResponse
from app.services.cache import APP_CACHE
from app.services.workbench import ensure_reference_data

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=201)
async def create_run(body: RunCreate, db: AsyncSession = Depends(get_db)):
    """Create a new pipeline run."""
    valid_modes = {"full_rerun", "partial_rerun", "sample_rerun", "pseudo_daily"}
    if body.run_mode not in valid_modes:
        raise HTTPException(400, f"Invalid run_mode. Must be one of: {valid_modes}")

    await ensure_reference_data(db)
    defaults = await db.execute(text("""
        SELECT
            (SELECT id FROM workbench.wb_parameter_set WHERE is_active = true ORDER BY id DESC LIMIT 1) AS parameter_set_id,
            (SELECT id FROM workbench.wb_rule_set ORDER BY id DESC LIMIT 1) AS rule_set_id,
            (SELECT id FROM workbench.wb_sql_bundle ORDER BY id DESC LIMIT 1) AS sql_bundle_id,
            (SELECT id FROM workbench.wb_contract ORDER BY id DESC LIMIT 1) AS contract_id
    """))
    default_row = defaults.mappings().first()
    payload = body.model_dump()
    if default_row:
        payload["parameter_set_id"] = payload.get("parameter_set_id") or default_row["parameter_set_id"]
        payload["rule_set_id"] = payload.get("rule_set_id") or default_row["rule_set_id"]
        payload["sql_bundle_id"] = payload.get("sql_bundle_id") or default_row["sql_bundle_id"]
        payload["contract_id"] = payload.get("contract_id") or default_row["contract_id"]

    result = await db.execute(text("""
        INSERT INTO workbench.wb_run
            (run_mode, origin_scope, parameter_set_id, rule_set_id, sql_bundle_id,
             contract_id, baseline_id, input_window_start, input_window_end,
             compare_run_id, rerun_from_step, sample_set_id, pseudo_daily_anchor,
             note, triggered_by)
        VALUES
            (:run_mode, :origin_scope, :parameter_set_id, :rule_set_id, :sql_bundle_id,
             :contract_id, :baseline_id, :input_window_start, :input_window_end,
             :compare_run_id, :rerun_from_step, :sample_set_id, :pseudo_daily_anchor,
             :note, 'api')
        RETURNING *
    """), payload)
    await db.commit()
    await APP_CACHE.invalidate()
    row = result.mappings().first()
    return RunOut(**row)


@router.get("", response_model=PaginatedResponse)
async def list_runs(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    wheres, params = [], {}
    if status:
        wheres.append("status = :status")
        params["status"] = status
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    cnt = await db.execute(text(f"SELECT count(*) FROM workbench.wb_run {where_clause}"), params)
    total = cnt.scalar()

    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    result = await db.execute(text(f"""
        SELECT * FROM workbench.wb_run {where_clause}
        ORDER BY started_at DESC
        LIMIT :lim OFFSET :off
    """), params)
    data = [RunOut(**r) for r in result.mappings().all()]
    return PaginatedResponse(total=total, page=page, page_size=page_size, data=data)


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM workbench.wb_run WHERE run_id = :id"), {"id": run_id}
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, f"Run {run_id} not found")
    return RunOut(**row)


@router.patch("/{run_id}/status")
async def update_run_status(run_id: int, status: str, db: AsyncSession = Depends(get_db)):
    """更新 run 状态。当状态变为 completed 时，自动触发快照刷新。"""
    valid = {"running", "completed", "failed", "cancelled"}
    if status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid}")
    result = await db.execute(text("""
        UPDATE workbench.wb_run
        SET status = :status,
            finished_at = CASE WHEN :status IN ('completed','failed','cancelled') THEN now() ELSE finished_at END,
            duration_seconds = CASE WHEN :status IN ('completed','failed','cancelled')
                THEN extract(epoch FROM now() - started_at)::int ELSE duration_seconds END
        WHERE run_id = :id
        RETURNING run_id, status
    """), {"status": status, "id": run_id})
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, f"Run {run_id} not found")
    await db.commit()
    await APP_CACHE.invalidate()

    # run 完成后自动触发快照刷新（工作台快照 + 源字段合规快照）
    snapshot_result = None
    if status == "completed":
        from app.services.workbench import refresh_all

        snapshot_result = await refresh_all(db, run_id=run_id, include_fields=True)

    return {
        "run_id": row["run_id"],
        "status": row["status"],
        "snapshot_refreshed": snapshot_result is not None and snapshot_result.get("snapshot", {}).get("refreshed", False),
    }
