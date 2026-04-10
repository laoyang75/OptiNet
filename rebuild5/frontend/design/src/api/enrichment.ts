import { apiGet, apiPost } from './client'

export interface EnrichmentVersion {
  run_id: string
  dataset_key: string
  snapshot_version: string
  snapshot_version_prev: string
}

export interface EnrichmentStatsPayload {
  version: EnrichmentVersion
  summary: {
    total_path_a: number
    donor_matched_count: number
    gps_filled: number
    rsrp_filled: number
    rsrq_filled: number
    sinr_filled: number
    operator_filled: number
    lac_filled: number
    tech_filled: number
    gps_anomaly_count: number
    collision_skip_anomaly_count: number
    donor_excellent_count: number
    donor_qualified_count: number
    remaining_none_gps: number
    remaining_none_signal: number
  }
  coverage: {
    gps_fill_rate: number
    signal_fill_rate: number
    operator_fill_rate: number
  }
}

export interface EnrichmentCoverageItem {
  field_name: string
  filled_count: number
  fill_rate: number
  donor_source: string
}

export interface EnrichmentCoveragePayload {
  items: EnrichmentCoverageItem[]
}

export interface EnrichmentAnomalyItem {
  batch_id: number
  record_id: string
  operator_code: string | null
  lac: number | null
  bs_id: number | null
  cell_id: number | null
  dev_id: string | null
  event_time_std: string | null
  lon_raw: number | null
  lat_raw: number | null
  donor_center_lon: number | null
  donor_center_lat: number | null
  distance_to_donor_m: number | null
  anomaly_type: string | null
  anomaly_threshold_m: number | null
  anomaly_source: string | null
  is_collision_id: boolean | null
  donor_snapshot_version: string | null
}

export interface EnrichmentAnomaliesPayload {
  items: EnrichmentAnomalyItem[]
  limit: number
}

export function getEnrichmentStats(): Promise<EnrichmentStatsPayload> {
  return apiGet<EnrichmentStatsPayload>('/api/enrichment/stats')
}

export function getEnrichmentCoverage(): Promise<EnrichmentCoveragePayload> {
  return apiGet<EnrichmentCoveragePayload>('/api/enrichment/coverage')
}

export function getEnrichmentAnomalies(limit = 200): Promise<EnrichmentAnomaliesPayload> {
  return apiGet<EnrichmentAnomaliesPayload>(`/api/enrichment/anomalies?limit=${limit}`)
}

export function runEnrichment(): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>>('/api/enrichment/run')
}
