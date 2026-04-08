"""Workbench APIs for versions, cache refresh, field governance, and sample research."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.cache import APP_CACHE
from app.services.workbench import (
    get_field_detail,
    get_sample_object_detail,
    get_sample_set_detail,
    get_version_change_log,
    get_version_context,
    get_version_history,
    list_fields,
    list_sample_sets,
    refresh_all,
)

router = APIRouter(tags=["workbench"])


@router.get("/version/current")
async def current_version_context(
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    key = f"version:current:{run_id}:{compare_run_id}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        60,
        lambda: get_version_context(db, run_id=run_id, compare_run_id=compare_run_id),
    )
    return {**data, "cache_hit": cache_hit}


@router.get("/version/change-log")
async def version_change_log(
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取两次 run 之间的版本变化摘要。"""
    key = f"version:change-log:{run_id}:{compare_run_id}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        120,
        lambda: get_version_change_log(db, run_id=run_id, compare_run_id=compare_run_id),
    )
    return {**data, "cache_hit": cache_hit}


@router.get("/version/history")
async def version_history(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    key = f"version:history:{limit}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        120,
        lambda: get_version_history(db, limit=limit),
    )
    return {"items": data, "cache_hit": cache_hit}


@router.post("/cache/refresh")
async def refresh_cache(
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """刷新快照。repair 仅允许 latest completed run，历史 run 默认只读。"""
    from app.services.workbench import latest_completed_run_id

    if run_id is not None:
        latest_id = await latest_completed_run_id(db)
        if latest_id is not None and run_id != latest_id:
            raise HTTPException(
                400,
                f"只允许重算最新完成的 run（#{latest_id}），历史 run #{run_id} 默认只读。",
            )

    result = await refresh_all(db, run_id=run_id, include_fields=True)
    await APP_CACHE.invalidate()
    return result


@router.get("/fields")
async def field_list(
    search: str | None = None,
    table_name: str | None = None,
    lifecycle_status: str | None = None,
    step_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    key = f"fields:{search}:{table_name}:{lifecycle_status}:{step_id}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        600,
        lambda: list_fields(
            db,
            search=search,
            table_name=table_name,
            lifecycle_status=lifecycle_status,
            step_id=step_id,
        ),
    )
    return {**data, "cache_hit": cache_hit}


@router.get("/fields/{field_name}")
async def field_detail(
    field_name: str,
    table_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    key = f"field:{field_name}:{table_name}"
    try:
        data, cache_hit = await APP_CACHE.get_or_set(
            key,
            600,
            lambda: get_field_detail(db, field_name, table_name),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if data is None:
        raise HTTPException(404, f"Field {field_name} not found")
    return {**data, "cache_hit": cache_hit}


@router.get("/samples")
async def sample_list(
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    data, cache_hit = await APP_CACHE.get_or_set(
        f"samples:list:{run_id}",
        300,
        lambda: list_sample_sets(db, run_id=run_id),
    )
    return {**data, "cache_hit": cache_hit}


@router.get("/samples/{sample_set_id}")
async def sample_detail(
    sample_set_id: int,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    key = f"samples:detail:{sample_set_id}:{run_id}:{compare_run_id}:{limit}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: get_sample_set_detail(
            db,
            sample_set_id,
            run_id=run_id,
            compare_run_id=compare_run_id,
            limit=limit,
        ),
    )
    if data is None:
        raise HTTPException(404, f"Sample set {sample_set_id} not found")
    return {**data, "cache_hit": cache_hit}


@router.get("/samples/{sample_set_id}/objects/{object_key:path}")
async def sample_object_detail(
    sample_set_id: int,
    object_key: str,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    key = f"samples:object:{sample_set_id}:{object_key}:{run_id}:{compare_run_id}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: get_sample_object_detail(
            db,
            sample_set_id,
            object_key,
            run_id=run_id,
            compare_run_id=compare_run_id,
        ),
    )
    if data is None:
        raise HTTPException(404, f"Sample object {object_key} not found")
    return {**data, "cache_hit": cache_hit}
