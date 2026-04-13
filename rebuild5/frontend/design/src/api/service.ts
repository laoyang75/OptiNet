import { apiGet } from './client'

export interface ServiceVersion {
  run_id: string
  dataset_key: string
  snapshot_version: string
  snapshot_version_prev: string
}

export interface ServiceSearchItem {
  level: 'cell' | 'bs' | 'lac'
  operator_code: string
  operator_cn: string | null
  lac: number | null
  bs_id: number | null
  cell_id: number | null
  tech_norm: string | null
  lifecycle_state: string
  position_grade: string | null
  center_lon: number | null
  center_lat: number | null
  p90_radius_m: number | null
  anchor_eligible: boolean
  baseline_eligible: boolean
  drift_pattern: string | null
  is_collision: boolean
  is_dynamic: boolean
  is_multi_centroid: boolean
  total_cells?: number
  qualified_cells?: number
  excellent_cells?: number
  total_bs?: number
  qualified_bs?: number
  qualified_bs_ratio?: number
}

export interface ServiceSearchPayload {
  version: ServiceVersion
  query: {
    q: string
    level: string
    operator_code: string | null
    limit?: number
    page?: number
    page_size?: number
  }
  items: ServiceSearchItem[]
  total_count?: number
  total_pages?: number
}

export interface ServiceCoveragePayload {
  version: ServiceVersion
  summary: {
    trusted_cell_total: number
    lac_total: number
    avg_p90: number
  }
  operators: Array<{
    operator_code: string
    operator_cn: string | null
    cells: number
    qualified_pct: number
    excellent_pct: number
    avg_p90: number
  }>
}

export interface ServiceReportRow {
  operator_code: string
  operator_cn: string | null
  lac: number
  cell_total: number
  qualified_cell_total: number
  excellent_cell_total: number
  bs_total: number
  qualified_bs_total: number
  avg_p90: number
}

export interface ServiceReportPayload {
  version: ServiceVersion
  rows: ServiceReportRow[]
}

export interface BSCellItem {
  cell_id: number
  lifecycle_state: string
  position_grade: string | null
  p90_radius_m: number | null
  drift_pattern: string | null
  is_collision: boolean
  is_multi_centroid: boolean
}

export interface LACBSItem {
  bs_id: number
  lifecycle_state: string
  classification: string | null
  total_cells: number
  qualified_cells: number
  excellent_cells: number
  anomaly_cell_ratio: number | null
}

export interface ServiceCellDetail {
  cell_id: number
  operator_code?: string
  operator_cn?: string | null
  lac?: number
  bs_id?: number | null
  tech_norm?: string | null
  lifecycle_state?: string
  position_grade?: string | null
  center_lon?: number | null
  center_lat?: number | null
  p50_radius_m?: number | null
  p90_radius_m?: number | null
  drift_pattern?: string | null
  anchor_eligible?: boolean
  baseline_eligible?: boolean
  is_collision?: boolean
  is_multi_centroid?: boolean
  is_dynamic?: boolean
  rsrp_avg?: number | null
  rsrq_avg?: number | null
  sinr_avg?: number | null
  pressure_avg?: number | null
  independent_obs?: number | null
  distinct_dev_id?: number | null
  active_days_30d?: number | null
}

export interface ServiceBSDetail {
  bs_id: number
  operator_code?: string
  operator_cn?: string | null
  lac?: number
  lifecycle_state?: string
  classification?: string | null
  total_cells?: number
  qualified_cells?: number
  excellent_cells?: number
  center_lon?: number | null
  center_lat?: number | null
  gps_p90_dist_m?: number | null
  anchor_eligible?: boolean
  baseline_eligible?: boolean
  anomaly_cell_ratio?: number | null
  cells: BSCellItem[]
}

export interface ServiceLACDetail {
  lac: number
  operator_code?: string
  operator_cn?: string | null
  lifecycle_state?: string
  total_bs?: number
  qualified_bs?: number
  qualified_bs_ratio?: number
  anomaly_bs_ratio?: number | null
  trend?: string | null
  anchor_eligible?: boolean
  baseline_eligible?: boolean
  bs_items: LACBSItem[]
}

export function getServiceSearch(q = '', level = 'cell', operatorCode?: string | null, page = 1, pageSize = 50): Promise<ServiceSearchPayload> {
  const params = new URLSearchParams({ q, level, page: String(page), page_size: String(pageSize) })
  if (operatorCode) params.set('operator_code', operatorCode)
  return apiGet<ServiceSearchPayload>(`/api/service/search?${params.toString()}`)
}

export function getServiceCell(
  cellId: number,
  context?: { operator_code?: string | null; lac?: number | null; tech_norm?: string | null },
): Promise<ServiceCellDetail> {
  const params = new URLSearchParams()
  if (context?.operator_code) params.set('operator_code', context.operator_code)
  if (context?.lac != null) params.set('lac', String(context.lac))
  if (context?.tech_norm) params.set('tech_norm', context.tech_norm)
  const qs = params.toString()
  return apiGet<ServiceCellDetail>(`/api/service/cell/${cellId}${qs ? `?${qs}` : ''}`)
}

export function getServiceBS(
  bsId: number,
  context?: { operator_code?: string | null; lac?: number | null },
): Promise<ServiceBSDetail> {
  const params = new URLSearchParams()
  if (context?.operator_code) params.set('operator_code', context.operator_code)
  if (context?.lac != null) params.set('lac', String(context.lac))
  const qs = params.toString()
  return apiGet<ServiceBSDetail>(`/api/service/bs/${bsId}${qs ? `?${qs}` : ''}`)
}

export function getServiceLAC(lac: number, context?: { operator_code?: string | null }): Promise<ServiceLACDetail> {
  const params = new URLSearchParams()
  if (context?.operator_code) params.set('operator_code', context.operator_code)
  const qs = params.toString()
  return apiGet<ServiceLACDetail>(`/api/service/lac/${lac}${qs ? `?${qs}` : ''}`)
}

export function getServiceCoverage(): Promise<ServiceCoveragePayload> {
  return apiGet<ServiceCoveragePayload>('/api/service/coverage')
}

export function getServiceReport(): Promise<ServiceReportPayload> {
  return apiGet<ServiceReportPayload>('/api/service/report')
}
