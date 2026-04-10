import { apiGet, apiGetPaged, apiPost } from './client'

export interface MaintenanceVersion {
  run_id: string
  dataset_key: string
  snapshot_version: string
  snapshot_version_prev: string
}

export interface MaintenanceStatsPayload {
  version: MaintenanceVersion
  summary: {
    published_cell_count: number
    published_bs_count: number
    published_lac_count: number
    collision_cell_count: number
    multi_centroid_cell_count: number
    dynamic_cell_count: number
    anomaly_bs_count: number
  }
  drift_distribution: Record<string, number>
}

export interface MaintenanceCellItem {
  operator_code: string
  operator_cn: string | null
  lac: number
  bs_id: number | null
  cell_id: number
  tech_norm: string | null
  lifecycle_state: string
  position_grade: string | null
  anchor_eligible: boolean
  baseline_eligible: boolean
  p50_radius_m: number | null
  p90_radius_m: number | null
  center_lon: number | null
  center_lat: number | null
  drift_pattern: string | null
  gps_anomaly_type: string | null
  is_collision: boolean
  is_dynamic: boolean
  is_multi_centroid: boolean
  antitoxin_hit: boolean
  cell_scale: string | null
  window_obs_count: number
  last_observed_at: string | null
  independent_obs: number | null
  distinct_dev_id: number | null
  max_spread_m: number | null
  net_drift_m: number | null
  drift_ratio: number | null
  pressure_avg: number | null
  active_days_30d: number
  consecutive_inactive_days: number
}

export interface MaintenanceCellsPayload {
  items: MaintenanceCellItem[]
  kind: string
  limit: number
}

export interface MaintenanceBSItem {
  operator_code: string
  operator_cn: string | null
  lac: number
  bs_id: number
  lifecycle_state: string
  anchor_eligible: boolean
  baseline_eligible: boolean
  total_cells: number
  qualified_cells: number
  excellent_cells: number
  center_lon: number | null
  center_lat: number | null
  gps_p50_dist_m: number | null
  gps_p90_dist_m: number | null
  classification: string | null
  anomaly_cell_ratio: number | null
  large_spread: boolean
  is_multi_centroid: boolean
  window_active_cell_count: number
  position_grade: string | null
}

export interface MaintenanceBSPayload {
  items: MaintenanceBSItem[]
  limit: number
}

export interface MaintenanceLACItem {
  operator_code: string
  operator_cn: string | null
  lac: number
  lifecycle_state: string
  anchor_eligible: boolean
  baseline_eligible: boolean
  total_bs: number
  qualified_bs: number
  qualified_bs_ratio: number
  area_km2: number | null
  anomaly_bs_ratio: number | null
  trend: string | null
  boundary_stability_score: number | null
  active_bs_count: number
  retired_bs_count: number
}

export interface MaintenanceLACPayload {
  items: MaintenanceLACItem[]
  limit: number
}

export interface CollisionItem {
  batch_id: number
  snapshot_version: string
  cell_id: number
  collision_combo_count: number
  dominant_combo: string | null
  combo_keys_json: Array<Record<string, unknown>>
}

export interface CollisionPayload {
  items: CollisionItem[]
  limit: number
}

export interface DriftPayload {
  distribution: Record<string, number>
}

export function getMaintenanceStats(): Promise<MaintenanceStatsPayload> {
  return apiGet<MaintenanceStatsPayload>('/api/maintenance/stats')
}

export async function getMaintenanceCells(kind = 'all', page = 1, pageSize = 50): Promise<MaintenanceCellsPayload & { totalCount: number; totalPages: number }> {
  const result = await apiGetPaged<MaintenanceCellsPayload>(`/api/maintenance/cells?kind=${encodeURIComponent(kind)}&page=${page}&page_size=${pageSize}`)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

export async function getMaintenanceBS(page = 1, pageSize = 50): Promise<MaintenanceBSPayload & { totalCount: number; totalPages: number }> {
  const result = await apiGetPaged<MaintenanceBSPayload>(`/api/maintenance/bs?page=${page}&page_size=${pageSize}`)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

export async function getMaintenanceLAC(page = 1, pageSize = 50): Promise<MaintenanceLACPayload & { totalCount: number; totalPages: number }> {
  const result = await apiGetPaged<MaintenanceLACPayload>(`/api/maintenance/lac?page=${page}&page_size=${pageSize}`)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

export async function getCollisionList(page = 1, pageSize = 50): Promise<CollisionPayload & { totalCount: number; totalPages: number }> {
  const result = await apiGetPaged<CollisionPayload>(`/api/maintenance/collision?page=${page}&page_size=${pageSize}`)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

export function getDriftDistribution(): Promise<DriftPayload> {
  return apiGet<DriftPayload>('/api/maintenance/drift')
}

export function runMaintenance(): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>>('/api/maintenance/run')
}

export interface AntitoxinHitItem {
  operator_code: string
  operator_cn: string | null
  lac: number
  bs_id: number | null
  cell_id: number
  tech_norm: string | null
  lifecycle_state: string
  drift_pattern: string | null
  max_spread_m: number | null
  centroid_shift_m: number | null
  p90_ratio: number | null
  prev_p90_radius_m: number | null
  curr_p90_radius_m: number | null
  dev_ratio: number | null
  prev_distinct_dev_id: number | null
  curr_distinct_dev_id: number | null
}

export interface AntitoxinHitPayload {
  items: AntitoxinHitItem[]
}

export interface ExitWarningItem {
  operator_code: string
  operator_cn: string | null
  lac: number
  bs_id: number | null
  cell_id: number
  tech_norm: string | null
  lifecycle_state: string
  active_days_30d: number
  consecutive_inactive_days: number
  window_obs_count: number
  last_observed_at: string | null
  density_level: string
  dormant_threshold_days: number
  urgency_ratio: number
}

export interface ExitWarningPayload {
  items: ExitWarningItem[]
}

export async function getAntitoxinHits(page = 1, pageSize = 50): Promise<AntitoxinHitPayload & { totalCount: number; totalPages: number }> {
  const result = await apiGetPaged<AntitoxinHitPayload>(`/api/maintenance/antitoxin-hits?page=${page}&page_size=${pageSize}`)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

export async function getExitWarnings(page = 1, pageSize = 50): Promise<ExitWarningPayload & { totalCount: number; totalPages: number }> {
  const result = await apiGetPaged<ExitWarningPayload>(`/api/maintenance/exit-warnings?page=${page}&page_size=${pageSize}`)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}
