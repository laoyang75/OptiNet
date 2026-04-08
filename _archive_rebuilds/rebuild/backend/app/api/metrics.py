"""Metrics APIs backed by workbench snapshot tables."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.cache import APP_CACHE
from app.services.workbench import (
    list_anomaly_summary,
    list_layer_snapshot,
    list_step_summary,
)
from app.services.workbench.base import fetch_all
from app.services.workbench.catalog import latest_completed_run_id, latest_run_id

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/layer-snapshot")
async def get_layer_snapshot(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    key = f"metrics:layer-snapshot:{run_id}:{refresh}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_layer_snapshot(db, run_id=run_id, force=refresh),
    )
    return [
        {
            **row,
            "cache_hit": cache_hit,
        }
        for row in data
    ]


@router.get("/step-summary")
async def get_step_summary(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    key = f"metrics:step-summary:{run_id}:{refresh}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_step_summary(db, run_id=run_id, force=refresh),
    )
    return [
        {
            **row,
            "cache_hit": cache_hit,
        }
        for row in data
    ]


@router.get("/anomaly-summary")
async def get_anomaly_summary(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    key = f"metrics:anomaly-summary:{run_id}:{refresh}"
    data, cache_hit = await APP_CACHE.get_or_set(
        key,
        300,
        lambda: list_anomaly_summary(db, run_id=run_id, force=refresh),
    )
    return [
        {
            **row,
            "cache_hit": cache_hit,
        }
        for row in data
    ]


@router.get("/gate-results")
async def get_gate_results(
    run_id: int | None = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """获取 Gate 门控检查结果。"""
    selected = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    rows = await fetch_all(db, """
        SELECT gate_code, gate_name, severity, expected_rule, actual_value, pass_flag, remark
        FROM workbench.wb_gate_result
        WHERE run_id = :run_id
        ORDER BY severity DESC, gate_code
    """, {"run_id": selected})
    return {"run_id": selected, "gates": rows}
