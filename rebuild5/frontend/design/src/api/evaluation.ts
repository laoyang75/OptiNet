import { apiGet, apiGetPaged } from './client'
import type { LifecycleState } from '../types'

/* ---------- helpers ---------- */

function batchQs(batchId?: number): string {
  return batchId != null ? `batch_id=${batchId}` : ''
}

function joinQs(base: string, ...parts: string[]): string {
  const qs = parts.filter(Boolean).join('&')
  return qs ? `${base}${base.includes('?') ? '&' : '?'}${qs}` : base
}

/* ---------- Batch ---------- */

export interface BatchItem {
  batch_id: number
  snapshot_version: string
  run_at: string
  dataset_key: string
}

export interface BatchesPayload {
  batches: BatchItem[]
}

export function fetchBatches(): Promise<BatchesPayload> {
  return apiGet<BatchesPayload>('/api/evaluation/batches')
}

/* ---------- Rule Impact ---------- */

export interface RuleImpactItem {
  rule: string
  threshold: string | number
  blocked: number
  desc: string
}

export interface RuleImpactPayload {
  rules: Record<string, number | string>
  impact: RuleImpactItem[]
}

export function fetchCellRuleImpact(batchId?: number): Promise<RuleImpactPayload> {
  return apiGet<RuleImpactPayload>(joinQs('/api/evaluation/cells/rule-impact', batchQs(batchId)))
}

export function fetchBSRuleImpact(batchId?: number): Promise<RuleImpactPayload> {
  return apiGet<RuleImpactPayload>(joinQs('/api/evaluation/bs/rule-impact', batchQs(batchId)))
}

export function fetchLACRuleImpact(batchId?: number): Promise<RuleImpactPayload> {
  return apiGet<RuleImpactPayload>(joinQs('/api/evaluation/lac/rule-impact', batchQs(batchId)))
}

/* ---------- Trend ---------- */

export interface TrendPoint {
  batch_id: number
  snapshot_version: string
  run_at: string
  cell: Record<LifecycleState, number>
  bs: Record<LifecycleState, number>
  lac: Record<LifecycleState, number>
  anchor_eligible_cells: number
}

export interface TrendPayload {
  points: TrendPoint[]
}

export async function fetchTrend(): Promise<TrendPayload> {
  const raw = await apiGet<{ points?: TrendPoint[]; batches?: TrendPoint[] }>('/api/evaluation/trend')
  return { points: raw.points ?? raw.batches ?? [] }
}

/* ---------- Overview ---------- */

export interface EvaluationOverviewPayload {
  dataset_key: string
  run_id: string
  snapshot_version: string
  snapshot_version_prev: string
  cell_distribution: Record<LifecycleState, number>
  bs_distribution: Record<LifecycleState, number>
  lac_distribution: Record<LifecycleState, number>
  diff_summary: {
    new: number
    promoted: number
    demoted: number
    eligibility_changed: number
    geometry_changed: number
    unchanged: number
  }
  counts: {
    cell_total: number
    bs_total: number
    lac_total: number
    anchor_eligible_cells: number
  }
  cleanup: {
    waiting_pruned_cells: number
    dormant_marked_cells: number
  }
}

export function getEvaluationOverview(batchId?: number): Promise<EvaluationOverviewPayload> {
  return apiGet<EvaluationOverviewPayload>(joinQs('/api/evaluation/overview', batchQs(batchId)))
}

/* ---------- Snapshot (kept for type compat during migration) ---------- */

export interface SnapshotItem {
  cell_id: string
  lac: string
  operator_code: string
  tech_norm?: string | null
  prev: LifecycleState | null
  curr: LifecycleState | null
  diff_kind: string
  reason: string
}

export interface SnapshotPayload {
  snapshot_version: string
  snapshot_version_prev: string
  summary: {
    new: number
    promoted: number
    demoted: number
    eligibility_changed?: number
    geometry_changed?: number
    unchanged: number
  }
  items: SnapshotItem[]
}

export function getEvaluationSnapshot(batchId?: number): Promise<SnapshotPayload> {
  return apiGet<SnapshotPayload>(joinQs('/api/evaluation/snapshot', batchQs(batchId)))
}

/* ---------- Watchlist ---------- */

export interface WatchItem {
  cell_id: string
  lac: string
  op: string
  state: LifecycleState
  obs: number
  devs: number
  p90: number
  span_h: number
  gap: string
}

export interface WatchlistPayload {
  items: WatchItem[]
  rules: Record<string, number>
}

export function getEvaluationWatchlist(batchId?: number): Promise<WatchlistPayload> {
  return apiGet<WatchlistPayload>(joinQs('/api/evaluation/watchlist', batchQs(batchId)))
}

/* ---------- Cell ---------- */

export interface CellEvaluationItem {
  operator_code: string
  lac: string
  cell_id: string
  bs_id: string
  tech_norm: string
  lifecycle_state: LifecycleState
  position_grade: string
  anchor_eligible: boolean
  baseline_eligible: boolean
  independent_obs: number
  distinct_dev_id: number
  gps_valid_count: number
  observed_span_hours: number
  p50_radius_m: number
  p90_radius_m: number
  center_lon: number | null
  center_lat: number | null
  active_days: number
  rsrp_avg: number | null
  is_collision_id: boolean
}

export interface CellEvaluationPayload {
  distribution: Record<LifecycleState, number>
  summary: {
    total: number
    anchor_eligible: number
  }
  items: CellEvaluationItem[]
}

export async function getCellEvaluation(page = 1, pageSize = 50, batchId?: number): Promise<CellEvaluationPayload & { totalCount: number; totalPages: number }> {
  const url = joinQs(`/api/evaluation/cells?page=${page}&page_size=${pageSize}`, batchQs(batchId))
  const result = await apiGetPaged<CellEvaluationPayload>(url)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

/* ---------- BS ---------- */

export interface BSEvaluationItem {
  operator_code: string
  lac: string
  bs_id: string
  lifecycle_state: LifecycleState
  anchor_eligible: boolean
  baseline_eligible: boolean
  total_cells: number
  qualified_cells: number
  excellent_cells: number
  center_lon: number | null
  center_lat: number | null
  large_spread: boolean
  classification: string
}

export interface BSEvaluationPayload {
  distribution: Record<LifecycleState, number>
  summary: {
    total: number
  }
  items: BSEvaluationItem[]
}

export async function getBSEvaluation(page = 1, pageSize = 50, batchId?: number): Promise<BSEvaluationPayload & { totalCount: number; totalPages: number }> {
  const url = joinQs(`/api/evaluation/bs?page=${page}&page_size=${pageSize}`, batchQs(batchId))
  const result = await apiGetPaged<BSEvaluationPayload>(url)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}

/* ---------- LAC ---------- */

export interface LACEvaluationItem {
  operator_code: string
  lac: string
  lifecycle_state: LifecycleState
  anchor_eligible: boolean
  total_bs: number
  qualified_bs: number
  qualified_bs_ratio: number
  area_km2: number
  anomaly_bs_ratio: number
}

export interface LACEvaluationPayload {
  distribution: Record<LifecycleState, number>
  summary: {
    total: number
  }
  items: LACEvaluationItem[]
}

export async function getLACEvaluation(page = 1, pageSize = 50, batchId?: number): Promise<LACEvaluationPayload & { totalCount: number; totalPages: number }> {
  const url = joinQs(`/api/evaluation/lac?page=${page}&page_size=${pageSize}`, batchQs(batchId))
  const result = await apiGetPaged<LACEvaluationPayload>(url)
  return { ...result.data, totalCount: result.meta.total_count, totalPages: result.meta.total_pages }
}
