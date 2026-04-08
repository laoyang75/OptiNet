"""Six-field envelope and error response helpers."""
from typing import Any


def envelope(
    data: Any,
    *,
    data_origin: str = "real",
    origin_detail: str | None = None,
    subject_scope: str = "batch",
    subject_note: str | None = None,
    context: dict | None = None,
) -> dict:
    return {
        "data_origin": data_origin,
        "origin_detail": origin_detail,
        "subject_scope": subject_scope,
        "subject_note": subject_note,
        "context": context or {},
        "data": data,
    }


def error_response(error_code: str, error_message: str, request_path: str, contract_version: str) -> dict:
    return {
        "error_code": error_code,
        "error_message": error_message,
        "error_context": {
            "request_path": request_path,
            "contract_version": contract_version,
        },
    }
