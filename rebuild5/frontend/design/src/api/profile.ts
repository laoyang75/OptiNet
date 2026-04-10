import { apiGet, apiPost } from './client'

export interface RoutingSummary {
  input_record_count: number
  path_a_record_count: number
  path_b_record_count: number
  path_b_cell_count: number
  path_c_drop_count: number
  collision_candidate_count: number
  collision_path_a_match_count: number
  collision_pending_count: number
  collision_drop_count: number
}

export interface RoutingMetrics {
  avg_independent_obs: number
  avg_independent_devs: number
  avg_observed_span_hours: number
  avg_p50_radius_m: number
  avg_p90_radius_m: number
  avg_gps_original_ratio: number
  avg_signal_original_ratio: number
  path_b_complete_cell_count: number
  path_b_partial_cell_count: number
}

export interface RoutingPayload {
  summary: RoutingSummary
  path_b_metrics: RoutingMetrics
  rules: Record<string, unknown>
  version: {
    dataset_key: string
    run_id: string
    snapshot_version_prev: string
    snapshot_version: string
  }
}

export interface RunProfilePayload {
  run_id: string
  dataset_key: string
  batch_id: number
  snapshot_version: string
  trusted_snapshot_version_prev: string
  path_a_record_count: number
  path_b_record_count: number
  path_b_cell_count: number
  path_c_drop_count: number
  cell_waiting_count: number
  cell_qualified_count: number
  cell_excellent_count: number
  bs_qualified_count: number
  lac_qualified_count: number
}

export function getRoutingPayload(): Promise<RoutingPayload> {
  return apiGet<RoutingPayload>('/api/routing/stats')
}

export function runProfilePipeline(): Promise<RunProfilePayload> {
  return apiPost<RunProfilePayload>('/api/routing/run')
}
