"""Step 5 maintenance routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..core.envelope import success_envelope, error_envelope
from ..maintenance.pipeline import run_maintenance_pipeline
from ..maintenance.queries import (
    get_antitoxin_hits_payload,
    get_collision_payload,
    get_drift_payload,
    get_device_weighted_p90_payload,
    get_exit_warnings_payload,
    get_maintenance_bs_detail_payload,
    get_maintenance_bs_payload,
    get_maintenance_cell_detail_payload,
    get_maintenance_cells_payload,
    get_maintenance_lac_payload,
    get_maintenance_stats_payload,
)


router = APIRouter(prefix='/api/maintenance', tags=['maintenance'])


@router.post('/run')
def run_maintenance() -> dict[str, object]:
    return success_envelope(run_maintenance_pipeline())


@router.get('/stats')
def maintenance_stats() -> dict[str, object]:
    return success_envelope(get_maintenance_stats_payload())


@router.get('/cells')
def maintenance_cells(kind: str = Query('all'), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_maintenance_cells_payload(kind=kind, page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/cells/{cell_id}')
def maintenance_cell_detail(cell_id: int) -> dict[str, object]:
    data = get_maintenance_cell_detail_payload(cell_id)
    if data is None:
        return error_envelope('NOT_FOUND', f'Cell {cell_id} 未找到')
    return success_envelope(data)


@router.get('/device-weighted-p90')
def maintenance_device_weighted_p90(cell_id: int = Query(...)) -> dict[str, object]:
    data = get_device_weighted_p90_payload(cell_id)
    if data is None:
        return error_envelope('NOT_FOUND', f'Cell {cell_id} 未找到')
    return success_envelope(data)


@router.get('/bs')
def maintenance_bs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_maintenance_bs_payload(page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/bs/{bs_id}')
def maintenance_bs_detail(bs_id: int) -> dict[str, object]:
    data = get_maintenance_bs_detail_payload(bs_id)
    if data is None:
        return error_envelope('NOT_FOUND', f'BS {bs_id} 未找到')
    return success_envelope(data)


@router.get('/lac')
def maintenance_lac(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_maintenance_lac_payload(page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/collision')
def maintenance_collision(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_collision_payload(page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/drift')
def maintenance_drift() -> dict[str, object]:
    return success_envelope(get_drift_payload())


@router.get('/antitoxin-hits')
def maintenance_antitoxin_hits(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_antitoxin_hits_payload(page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/exit-warnings')
def maintenance_exit_warnings(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_exit_warnings_payload(page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)
