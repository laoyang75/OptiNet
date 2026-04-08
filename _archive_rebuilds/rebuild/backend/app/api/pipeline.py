"""Pipeline data APIs: overview, dim tables, profiles, fact table queries."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    PipelineOverview, TableStats, PaginatedResponse,
    TrustedLacOut, TrustedBsOut,
    LacProfileOut, BsProfileOut, CellProfileOut,
)
from app.services.cache import APP_CACHE
from app.services.labels import table_label
from app.services.workbench import (
    list_gps_status_distribution,
    list_operator_tech_distribution,
    list_signal_fill_distribution,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/overview", response_model=PipelineOverview)
async def get_pipeline_overview(db: AsyncSession = Depends(get_db)):
    """Get overview of all pipeline tables with row counts and sizes."""
    async def _builder():
        result = await db.execute(text("""
            SELECT
                schemaname AS schema_name,
                relname AS table_name,
                n_live_tup::bigint AS row_count,
                pg_total_relation_size(schemaname || '.' || relname) AS size_bytes,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) AS size_pretty
            FROM pg_stat_user_tables
            WHERE schemaname = 'pipeline'
            ORDER BY n_live_tup DESC
        """))
        rows = result.mappings().all()
        tables = [TableStats(table_name_cn=table_label(r["table_name"]), **r) for r in rows]
        return PipelineOverview(
            total_tables=len(tables),
            total_rows=sum(t.row_count for t in tables),
            tables=tables,
        )

    data, _ = await APP_CACHE.get_or_set("pipeline:overview", 300, _builder)
    return data


# ── Dim: Trusted LAC ────────────────────────────────────────────────

@router.get("/dim/lac-trusted", response_model=PaginatedResponse)
async def list_trusted_lac(
    operator: str | None = None,
    tech: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    wheres, params = [], {}
    if operator:
        wheres.append("operator_id_raw = :op")
        params["op"] = operator
    if tech:
        wheres.append("tech_norm = :tech")
        params["tech"] = tech
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    cnt = await db.execute(text(f"SELECT count(*) FROM pipeline.dim_lac_trusted {where_clause}"), params)
    total = cnt.scalar()

    q = f"""
        SELECT * FROM pipeline.dim_lac_trusted {where_clause}
        ORDER BY lac_confidence_rank ASC
        LIMIT :lim OFFSET :off
    """
    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    data = [TrustedLacOut(**r) for r in result.mappings().all()]
    return PaginatedResponse(total=total, page=page, page_size=page_size, data=data)


# ── Dim: Trusted BS ─────────────────────────────────────────────────

@router.get("/dim/bs-trusted", response_model=PaginatedResponse)
async def list_trusted_bs(
    tech: str | None = None,
    gps_level: str | None = None,
    collision_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    wheres, params = [], {}
    if tech:
        wheres.append("tech_norm = :tech")
        params["tech"] = tech
    if gps_level:
        wheres.append("gps_valid_level = :lvl")
        params["lvl"] = gps_level
    if collision_only:
        wheres.append("is_collision_suspect = true")
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    cnt = await db.execute(text(f"SELECT count(*) FROM pipeline.dim_bs_trusted {where_clause}"), params)
    total = cnt.scalar()

    q = f"""
        SELECT * FROM pipeline.dim_bs_trusted {where_clause}
        ORDER BY bs_id ASC
        LIMIT :lim OFFSET :off
    """
    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    data = [TrustedBsOut(**r) for r in result.mappings().all()]
    return PaginatedResponse(total=total, page=page, page_size=page_size, data=data)


# ── Profile: LAC ────────────────────────────────────────────────────

@router.get("/profile/lac", response_model=PaginatedResponse)
async def list_lac_profiles(
    operator: str | None = None,
    tech: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    wheres, params = [], {}
    if operator:
        wheres.append("operator_id_cn = :op")
        params["op"] = operator
    if tech:
        wheres.append("tech_norm = :tech")
        params["tech"] = tech
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    cnt = await db.execute(text(f"SELECT count(*) FROM pipeline.profile_lac {where_clause}"), params)
    total = cnt.scalar()

    q = f"""
        SELECT * FROM pipeline.profile_lac {where_clause}
        ORDER BY record_count DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """
    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    data = [LacProfileOut(**r) for r in result.mappings().all()]
    return PaginatedResponse(total=total, page=page, page_size=page_size, data=data)


# ── Profile: BS ─────────────────────────────────────────────────────

@router.get("/profile/bs", response_model=PaginatedResponse)
async def list_bs_profiles(
    operator: str | None = None,
    tech: str | None = None,
    lac: int | None = None,
    collision_only: bool = False,
    unstable_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    wheres, params = [], {}
    if operator:
        wheres.append("operator_id_cn = :op")
        params["op"] = operator
    if tech:
        wheres.append("tech_norm = :tech")
        params["tech"] = tech
    if lac is not None:
        wheres.append("lac_dec = :lac")
        params["lac"] = lac
    if collision_only:
        wheres.append("is_collision_suspect = true")
    if unstable_only:
        wheres.append("is_gps_unstable = true")
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    cnt = await db.execute(text(f"SELECT count(*) FROM pipeline.profile_bs {where_clause}"), params)
    total = cnt.scalar()

    q = f"""
        SELECT * FROM pipeline.profile_bs {where_clause}
        ORDER BY record_count DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """
    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    data = [BsProfileOut(**r) for r in result.mappings().all()]
    return PaginatedResponse(total=total, page=page, page_size=page_size, data=data)


# ── Profile: Cell ───────────────────────────────────────────────────

@router.get("/profile/cell", response_model=PaginatedResponse)
async def list_cell_profiles(
    operator: str | None = None,
    tech: str | None = None,
    lac: int | None = None,
    bs: int | None = None,
    dynamic_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    wheres, params = [], {}
    if operator:
        wheres.append("operator_id_cn = :op")
        params["op"] = operator
    if tech:
        wheres.append("tech_norm = :tech")
        params["tech"] = tech
    if lac is not None:
        wheres.append("lac_dec = :lac")
        params["lac"] = lac
    if bs is not None:
        wheres.append("bs_id = :bs")
        params["bs"] = bs
    if dynamic_only:
        wheres.append("is_dynamic_cell = true")
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    cnt = await db.execute(text(f"SELECT count(*) FROM pipeline.profile_cell {where_clause}"), params)
    total = cnt.scalar()

    q = f"""
        SELECT * FROM pipeline.profile_cell {where_clause}
        ORDER BY record_count DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """
    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    data = [CellProfileOut(**r) for r in result.mappings().all()]
    return PaginatedResponse(total=total, page=page, page_size=page_size, data=data)


# ── Stats: distribution summaries ───────────────────────────────────

@router.get("/stats/operator-tech")
async def get_operator_tech_stats(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats by operator + tech from snapshot metrics."""
    key = f"pipeline:stats:operator-tech:{run_id}:{refresh}"
    data, _ = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_operator_tech_distribution(db, run_id=run_id, force=refresh),
    )
    return data


@router.get("/stats/gps-status")
async def get_gps_status_distribution(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """GPS status distribution from snapshot metrics."""
    key = f"pipeline:stats:gps-status:{run_id}:{refresh}"
    data, _ = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_gps_status_distribution(db, run_id=run_id, force=refresh),
    )
    return data


@router.get("/stats/signal-fill")
async def get_signal_fill_distribution(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Signal fill source distribution from snapshot metrics."""
    key = f"pipeline:stats:signal-fill:{run_id}:{refresh}"
    data, _ = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_signal_fill_distribution(db, run_id=run_id, force=refresh),
    )
    return data
