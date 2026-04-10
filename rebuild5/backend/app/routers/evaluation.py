"""Evaluation Step 3 routes for rebuild5."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..core.envelope import success_envelope, error_envelope
from ..evaluation.pipeline import run_evaluation_only
from ..evaluation.queries import (
    get_batches_payload,
    get_bs_detail_payload,
    get_bs_evaluation_payload,
    get_bs_rule_impact_payload,
    get_cell_detail_payload,
    get_cell_evaluation_payload,
    get_cell_rule_impact_payload,
    get_evaluation_overview_payload,
    get_lac_detail_payload,
    get_lac_evaluation_payload,
    get_lac_rule_impact_payload,
    get_snapshot_payload,
    get_trend_payload,
    get_watchlist_payload,
)


router = APIRouter(prefix='/api/evaluation', tags=['evaluation'])


@router.post('/run')
def run_evaluation() -> dict[str, object]:
    return success_envelope(run_evaluation_only())


@router.get('/batches')
def batches() -> dict[str, object]:
    return success_envelope(get_batches_payload())


@router.get('/overview')
def overview(batch_id: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_evaluation_overview_payload(batch_id=batch_id))


@router.get('/trend')
def trend() -> dict[str, object]:
    return success_envelope(get_trend_payload())


@router.get('/snapshot')
def snapshot(batch_id: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_snapshot_payload(batch_id=batch_id))


@router.get('/watchlist')
def watchlist(batch_id: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_watchlist_payload(batch_id=batch_id))


@router.get('/cells/rule-impact')
def cells_rule_impact(batch_id: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_cell_rule_impact_payload(batch_id=batch_id))


@router.get('/cells/{cell_id}')
def cell_detail(cell_id: int, batch_id: int | None = Query(None)) -> dict[str, object]:
    data = get_cell_detail_payload(cell_id, batch_id=batch_id)
    if data is None:
        return error_envelope('NOT_FOUND', f'Cell {cell_id} 未找到')
    return success_envelope(data)


@router.get('/cells')
def cells(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), batch_id: int | None = Query(None)) -> dict[str, object]:
    payload = get_cell_evaluation_payload(page=page, page_size=page_size, batch_id=batch_id)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/bs/rule-impact')
def bs_rule_impact(batch_id: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_bs_rule_impact_payload(batch_id=batch_id))


@router.get('/bs/{bs_id}')
def bs_detail(bs_id: int, batch_id: int | None = Query(None)) -> dict[str, object]:
    data = get_bs_detail_payload(bs_id, batch_id=batch_id)
    if data is None:
        return error_envelope('NOT_FOUND', f'BS {bs_id} 未找到')
    return success_envelope(data)


@router.get('/bs')
def bs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), batch_id: int | None = Query(None)) -> dict[str, object]:
    payload = get_bs_evaluation_payload(page=page, page_size=page_size, batch_id=batch_id)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/lac/rule-impact')
def lac_rule_impact(batch_id: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_lac_rule_impact_payload(batch_id=batch_id))


@router.get('/lac/{lac_id}')
def lac_detail(lac_id: int, batch_id: int | None = Query(None)) -> dict[str, object]:
    data = get_lac_detail_payload(lac_id, batch_id=batch_id)
    if data is None:
        return error_envelope('NOT_FOUND', f'LAC {lac_id} 未找到')
    return success_envelope(data)


@router.get('/lac')
def lac(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), batch_id: int | None = Query(None)) -> dict[str, object]:
    payload = get_lac_evaluation_payload(page=page, page_size=page_size, batch_id=batch_id)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)
