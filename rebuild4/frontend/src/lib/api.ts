const BASE = '/api'

async function request<T = any>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok && res.status >= 500) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

function withQuery(path: string, q: Record<string, any>): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(q)) {
    if (v != null && v !== '') params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

// API-01
export const getFlowOverview = () => request(`${BASE}/flow-overview`)

// API-02
export const getFlowSnapshotTimepoints = () => request(`${BASE}/flow-snapshot/timepoints`)
export const getFlowSnapshot = (batchId: string) => request(withQuery(`${BASE}/flow-snapshot`, { batch_id: batchId }))

// API-03
export const getRunsCurrent = () => request(`${BASE}/runs/current`)
export const getBatches = (q?: Record<string, any>) => request(withQuery(`${BASE}/batches`, q || {}))
export const getBatchDetail = (id: string) => request(`${BASE}/batches/${id}/detail`)

// API-04 & 05
export const getObjects = (q?: Record<string, any>) => request(withQuery(`${BASE}/objects`, q || {}))
export const getObjectsSummary = (type: string) => request(withQuery(`${BASE}/objects/summary`, { type }))
export const getObjectDetail = (key: string) => request(`${BASE}/objects/${key}/detail`)

// API-06
export const getObservationWorkspace = (q?: Record<string, any>) => request(withQuery(`${BASE}/observation-workspace`, q || {}))

// API-07
export const getAnomalySummary = (view?: string) => request(withQuery(`${BASE}/anomaly-workspace/summary`, { view }))
export const getAnomalyWorkspace = (q?: Record<string, any>) => request(withQuery(`${BASE}/anomaly-workspace`, q || {}))
export const getAnomalyImpact = (key: string) => request(`${BASE}/anomaly-workspace/${key}/impact`)

// API-08
export const getBaselineCurrent = () => request(`${BASE}/baseline/current`)
export const getBaselineDiff = () => request(`${BASE}/baseline/current/diff`)
export const getBaselineHistory = (q?: Record<string, any>) => request(withQuery(`${BASE}/baseline/history`, q || {}))

// API-09
export const getProfileLac = (q?: Record<string, any>) => request(withQuery(`${BASE}/profiles/lac`, q || {}))
export const getProfileBs = (q?: Record<string, any>) => request(withQuery(`${BASE}/profiles/bs`, q || {}))
export const getProfileCell = (q?: Record<string, any>) => request(withQuery(`${BASE}/profiles/cell`, q || {}))

// API-10
export const getInitializationLatest = () => request(`${BASE}/initialization/latest`)
export const getInitializationDetail = (runId: string) => request(`${BASE}/initialization/${runId}`)

// API-11
export const getGovernanceOverview = () => request(`${BASE}/governance/overview`)
export const getGovernanceFields = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/fields`, q || {}))
export const getGovernanceTables = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/tables`, q || {}))
export const getGovernanceUsage = (tableName: string) => request(`${BASE}/governance/usage/${tableName}`)
export const getGovernanceMigration = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/migration`, q || {}))
export const getGovernanceFieldAudit = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/field_audit`, q || {}))
export const getGovernanceTargetFields = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/target_fields`, q || {}))
export const getGovernanceOdsRules = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/ods_rules`, q || {}))
export const getGovernanceOdsExecutions = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/ods_executions`, q || {}))
export const getGovernanceParseRules = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/parse_rules`, q || {}))
export const getGovernanceComplianceRules = (q?: Record<string, any>) => request(withQuery(`${BASE}/governance/compliance_rules`, q || {}))
export const getGovernanceTrustedLoss = (breakdownType?: string) => request(withQuery(`${BASE}/governance/trusted_loss`, { breakdown_type: breakdownType || 'overview' }))

// API-ETL 验证
export const getFoundationScopes = () => request(`${BASE}/governance/foundation/scopes`)
export const getFoundationRawOverview = () => request(`${BASE}/governance/foundation/raw-overview`)
export const getFoundationL0Audit = () => request(`${BASE}/governance/foundation/l0-audit`)
export const getFoundationL0Overview = () => request(`${BASE}/governance/foundation/l0-overview`)
export const getFoundationOdsRules = () => request(`${BASE}/governance/foundation/ods-rules`)
export const getEtlParseStats = () => request(`${BASE}/governance/foundation/etl/parse-stats`)
export const getEtlParseFields = () => request(`${BASE}/governance/foundation/etl/parse-fields`)
export const getEtlCleanStats = () => request(`${BASE}/governance/foundation/etl/clean-stats`)
export const getEtlFillStats = () => request(`${BASE}/governance/foundation/etl/fill-stats`)

// API-12
export const getValidationCompare = (q?: Record<string, any>) => request(withQuery(`${BASE}/validation/compare`, q || {}))

// System
export const getSystemStatus = () => request(`${BASE}/system/status`)
