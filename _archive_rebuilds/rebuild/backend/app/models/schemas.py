"""Pydantic schemas for API request/response models."""

from __future__ import annotations
from datetime import date, datetime
from typing import Any
from pydantic import BaseModel


# ── Run ──────────────────────────────────────────────────────────────

class RunCreate(BaseModel):
    run_mode: str  # full_rerun / partial_rerun / sample_rerun / pseudo_daily
    origin_scope: str = "layer0_start"
    parameter_set_id: int | None = None
    rule_set_id: int | None = None
    sql_bundle_id: int | None = None
    contract_id: int | None = None
    baseline_id: int | None = None
    input_window_start: date | None = None
    input_window_end: date | None = None
    compare_run_id: int | None = None
    rerun_from_step: str | None = None
    sample_set_id: int | None = None
    pseudo_daily_anchor: date | None = None
    note: str | None = None


class RunOut(BaseModel):
    run_id: int
    run_mode: str
    origin_scope: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    duration_seconds: int | None
    parameter_set_id: int | None
    rule_set_id: int | None
    sql_bundle_id: int | None
    contract_id: int | None
    baseline_id: int | None
    input_window_start: date | None
    input_window_end: date | None
    compare_run_id: int | None
    rerun_from_step: str | None
    sample_set_id: int | None
    note: str | None

    class Config:
        from_attributes = True


# ── Step Registry ────────────────────────────────────────────────────

class StepOut(BaseModel):
    step_id: str
    step_order: int
    step_name: str
    step_name_en: str
    layer: str
    is_main_chain: bool
    input_tables: list[str]
    output_tables: list[str]
    sql_file: str | None
    description: str | None = None

    class Config:
        from_attributes = True


# ── Pipeline Overview ────────────────────────────────────────────────

class TableStats(BaseModel):
    schema_name: str
    table_name: str
    table_name_cn: str | None = None
    row_count: int
    size_bytes: int | None = None
    size_pretty: str | None = None


class PipelineOverview(BaseModel):
    total_tables: int
    total_rows: int
    tables: list[TableStats]


# ── Metrics ──────────────────────────────────────────────────────────

class StepMetricOut(BaseModel):
    step_id: str
    metric_code: str
    metric_name: str
    dimension_key: str
    value_num: float | None
    value_text: str | None
    unit: str | None


class GateResultOut(BaseModel):
    gate_code: str
    gate_name: str
    severity: str
    expected_rule: str | None
    actual_value: float | None
    pass_flag: bool
    remark: str | None


# ── Profile ──────────────────────────────────────────────────────────

class LacProfileOut(BaseModel):
    operator_id_cn: str
    tech_norm: str
    lac_dec: int
    record_count: int | None
    active_days: int | None
    distinct_bs_count: int | None
    distinct_cell_count: int | None
    gps_valid_ratio: float | None
    gps_center_lon: float | None
    gps_center_lat: float | None
    is_insufficient_sample: bool | None
    is_gps_unstable: bool | None

    class Config:
        from_attributes = True


class BsProfileOut(BaseModel):
    operator_id_cn: str
    tech_norm: str
    lac_dec: int
    bs_id: int
    wuli_fentong_bs_key: str | None
    record_count: int | None
    active_days: int | None
    distinct_cell_count: int | None
    gps_valid_ratio: float | None
    gps_center_lon: float | None
    gps_center_lat: float | None
    gps_dist_p50_m: float | None
    gps_dist_p90_m: float | None
    is_collision_suspect: bool | None
    is_severe_collision: bool | None
    is_gps_unstable: bool | None
    is_multi_operator_shared: bool | None

    class Config:
        from_attributes = True


class CellProfileOut(BaseModel):
    operator_id_cn: str
    tech_norm: str
    lac_dec: int
    bs_id: int
    cell_id_dec: int
    record_count: int | None
    active_days: int | None
    gps_valid_ratio: float | None
    gps_center_lon: float | None
    gps_center_lat: float | None
    is_dynamic_cell: bool | None
    is_collision_suspect: bool | None
    is_insufficient_sample: bool | None

    class Config:
        from_attributes = True


# ── Dim tables ───────────────────────────────────────────────────────

class TrustedLacOut(BaseModel):
    operator_id_raw: str
    tech_norm: str
    lac_dec: int
    record_count: int | None
    valid_gps_count: int | None
    distinct_cellid_count: int | None
    distinct_device_count: int | None
    active_days: int | None
    lac_confidence_score: int | None
    lac_confidence_rank: int | None
    is_trusted_lac: bool | None

    class Config:
        from_attributes = True


class TrustedBsOut(BaseModel):
    tech_norm: str
    bs_id: int
    lac_dec_final: int
    wuli_fentong_bs_key: str | None
    gps_valid_level: str | None
    bs_center_lon: float | None
    bs_center_lat: float | None
    gps_p50_dist_m: float | None
    gps_p90_dist_m: float | None
    is_collision_suspect: bool | None
    collision_reason: str | None
    is_multi_operator_shared: bool | None
    active_days: int | None

    class Config:
        from_attributes = True


# ── Paginated response ───────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    data: list[Any]
