import { apiGet, apiPost } from './client'

export interface EtlSourceItem {
  id: string
  name: string
  type: string
  table: string
  status: string
  records: number
  lastSync: string
  fields: number
}

export interface EtlSourcePayload {
  sources: EtlSourceItem[]
  summary: {
    source_count: number
    raw_record_count: number
    last_sync: string
  }
}

export interface FieldAuditItem {
  name: string
  type: string
  decision: 'keep' | 'parse' | 'drop'
  coverage: number
  sample: string
}

export interface FieldAuditPayload {
  fields: FieldAuditItem[]
  decision_summary: Record<string, number>
  raw_field_count: number
}

export interface StatsSummary {
  source_count: number
  raw_record_count: number
  parsed_record_count: number
  cleaned_record_count: number
  filled_record_count: number
  clean_pass_rate: number
  field_coverage: Record<string, number>
}

export interface ParseSourceItem {
  name: string
  inputCount: number
  outputCount: number
  ratio: number
}

export interface EtlStatsPayload {
  summary: StatsSummary
  parse: {
    inputRecords: number
    outputRecords: number
    expansionRatio: number
    sources: ParseSourceItem[]
  }
  clean: {
    inputRecords: number
    passedRecords: number
    deletedRecords: number
    passRate: number
  }
  fill: Record<string, unknown>
}

export interface CleanRuleItem {
  rule_id: string
  rule_name: string
  description: string
  hit_count: number
  drop_count: number
  pass_rate: number
}

export interface CleanRulesPayload {
  rules: CleanRuleItem[]
  summary: {
    inputRecords: number
    passedRecords: number
    deletedRecords: number
    passRate: number
  }
}

export interface CoverageFieldItem {
  field: string
  before: number
  after: number
  source: string
  note: string
}

export interface CoveragePayload {
  fields: CoverageFieldItem[]
  source_distribution: {
    raw_gps: number
    ss1_own: number
    same_cell: number
    none: number
  }
  total_records: number
  time_window_seconds: number
}

export interface RunStep1Payload {
  run_id: string
  dataset_key: string
  raw_record_count: number
  parsed_record_count: number
  cleaned_record_count: number
  filled_record_count: number
  clean_deleted_count: number
  clean_pass_rate: number
}

export interface EtlRuleStatsItem {
  batch_id: number
  rule_code: string
  rule_desc: string
  hit_count: number
  total_rows: number | null
  hit_pct: number
  recorded_at: string | null
}

export interface EtlRuleStatsPayload {
  items: EtlRuleStatsItem[]
  batches: number[]
}

export function getEtlSource(): Promise<EtlSourcePayload> {
  return apiGet<EtlSourcePayload>('/api/etl/source')
}

export function getFieldAudit(): Promise<FieldAuditPayload> {
  return apiGet<FieldAuditPayload>('/api/etl/field-audit')
}

export function getEtlStats(): Promise<EtlStatsPayload> {
  return apiGet<EtlStatsPayload>('/api/etl/stats')
}

export function getCleanRules(): Promise<CleanRulesPayload> {
  return apiGet<CleanRulesPayload>('/api/etl/clean-rules')
}

export function getRuleStats(batchId?: number, ruleCode?: string): Promise<EtlRuleStatsPayload> {
  const params = new URLSearchParams()
  if (batchId != null && batchId > 0) params.set('batch_id', String(batchId))
  if (ruleCode) params.set('rule_code', ruleCode)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return apiGet<EtlRuleStatsPayload>(`/api/etl/rule-stats${suffix}`)
}

export function getEtlCoverage(): Promise<CoveragePayload> {
  return apiGet<CoveragePayload>('/api/etl/coverage')
}

export function runEtl(): Promise<RunStep1Payload> {
  return apiPost<RunStep1Payload>('/api/etl/run')
}
