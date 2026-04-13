"""Step 6 service routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..core.envelope import success_envelope
from ..service_query.queries import (
    get_service_bs_payload,
    get_service_cell_payload,
    get_service_coverage_payload,
    get_service_lac_payload,
    get_service_report_payload,
    search_service_payload,
)


router = APIRouter(prefix='/api/service', tags=['service'])


@router.get('/search')
def search_service(
    q: str | None = None,
    level: str = Query('cell'),
    operator_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    payload = search_service_payload(q=q, level=level, operator_code=operator_code, page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)


@router.get('/cell/{cell_id}')
def get_cell(
    cell_id: int,
    operator_code: str | None = None,
    lac: int | None = Query(None),
    tech_norm: str | None = None,
) -> dict[str, object]:
    return success_envelope(
        get_service_cell_payload(
            cell_id,
            operator_code=operator_code,
            lac=lac,
            tech_norm=tech_norm,
        )
    )


@router.get('/bs/{bs_id}')
def get_bs(bs_id: int, operator_code: str | None = None, lac: int | None = Query(None)) -> dict[str, object]:
    return success_envelope(get_service_bs_payload(bs_id, operator_code=operator_code, lac=lac))


@router.get('/lac/{lac}')
def get_lac(lac: int, operator_code: str | None = None) -> dict[str, object]:
    return success_envelope(get_service_lac_payload(lac, operator_code=operator_code))


@router.get('/coverage')
def coverage() -> dict[str, object]:
    return success_envelope(get_service_coverage_payload())


@router.get('/report')
def report() -> dict[str, object]:
    return success_envelope(get_service_report_payload())
