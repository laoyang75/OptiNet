"""源字段合规治理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.cache import APP_CACHE
from app.services.workbench import (
    get_source_field_detail,
    list_source_field_trend,
    list_source_fields,
    refresh_source_field_snapshots,
)

router = APIRouter(prefix="/source-fields", tags=["source-fields"])


@router.get("")
async def source_field_list(
    run_id: int | None = None,
    search: str | None = None,
    logical_domain: str | None = None,
    scope: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取源字段列表及最新合规率。"""
    key = f"source-fields:list:{run_id}:{search}:{logical_domain}:{scope}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_source_fields(
            db, run_id=run_id, search=search,
            logical_domain=logical_domain, scope=scope,
        ),
    )
    return {**data, "cache_hit": cache_hit}


@router.get("/{field_name}")
async def source_field_detail(
    field_name: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取单个源字段详情。"""
    key = f"source-fields:detail:{field_name}:{run_id}:{compare_run_id}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: get_source_field_detail(
            db, field_name, run_id=run_id, compare_run_id=compare_run_id,
        ),
    )
    if data is None:
        raise HTTPException(404, f"Source field {field_name} not found")
    return {**data, "cache_hit": cache_hit}


@router.get("/{field_name}/trend")
async def source_field_trend(
    field_name: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取源字段合规率趋势。"""
    key = f"source-fields:trend:{field_name}:{limit}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_source_field_trend(db, field_name, limit=limit),
    )
    return {**data, "cache_hit": cache_hit}


@router.post("/refresh")
async def refresh_source_fields(
    run_id: int | None = None,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """手动刷新源字段合规快照。"""
    try:
        result = await refresh_source_field_snapshots(db, run_id=run_id, force=force)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await APP_CACHE.invalidate("source-fields:")
    return result
