import { apiGet, apiPost } from './client'

export interface CurrentVersion {
  dataset_key: string
  run_id: string
  snapshot_version: string
  status: 'running' | 'completed' | 'verifying' | 'published' | 'reverted'
  updated_at: string
}

export interface DatasetMode {
  key: string
  label: string
  switch_supported: boolean
  message: string
  plan_doc: string
}

export interface DatasetItem {
  dataset_key: string
  source_desc: string
  imported_at: string
  record_count: number
  lac_scope: string
  time_range: string
  status: string
  is_current: boolean
  last_run_id?: string
  last_snapshot_version?: string
  last_run_status?: string
  last_updated_at?: string
}

export interface SystemConfigPayload {
  current_version: CurrentVersion
  dataset_mode: DatasetMode
  datasets: DatasetItem[]
  params: Record<string, unknown>
}

export interface RunLogItem {
  run_id: string
  run_type: string
  dataset_key: string
  snapshot_version: string | null
  status: string
  started_at: string | null
  finished_at: string | null
  step_chain: string | null
  result_summary?: Record<string, unknown>
}

export interface RunLogPayload {
  runs: RunLogItem[]
}

export interface PrepareSamplePayload {
  run_id: string
  dataset_key: string
  raw_lac_count: number
  raw_gps_count: number
  raw_record_count: number
}

export function getSystemConfig(): Promise<SystemConfigPayload> {
  return apiGet<SystemConfigPayload>('/api/system/config')
}

export function getRunLog(): Promise<RunLogPayload> {
  return apiGet<RunLogPayload>('/api/system/run-log')
}

export function prepareCurrentDataset(): Promise<PrepareSamplePayload> {
  return apiPost<PrepareSamplePayload>('/api/system/prepare-current-dataset')
}

export function prepareSampleDataset(): Promise<PrepareSamplePayload> {
  return prepareCurrentDataset()
}

export interface PipelineRunPayload {
  step1?: Record<string, unknown>
  step2_step3?: Record<string, unknown>
  step4?: Record<string, unknown>
  step5?: Record<string, unknown>
}

/**
 * Run pipeline from a given step.
 * from_step=1: full (Step 1-5), from_step=2: Step 2-5, from_step=5: Step 5 only
 */
export function runPipeline(fromStep: number = 1): Promise<PipelineRunPayload> {
  return apiPost<PipelineRunPayload>(`/api/pipeline/run?from_step=${fromStep}`)
}
