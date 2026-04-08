const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...JSON_HEADERS,
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function withQuery(path: string, query?: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  });
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export const api = {
  getCurrentRun: () => request('/api/v1/runs/current'),
  getFlowOverview: () => request('/api/v1/runs/flow-overview'),
  getFlowSnapshots: (query?: Record<string, string | number | undefined | null>) => request(withQuery('/api/v1/runs/flow-snapshots', query)),
  getBatches: () => request('/api/v1/runs/batches'),
  getBatchDetail: (batchId: string) => request(`/api/v1/runs/batch/${batchId}`),
  getObservationWorkspace: () => request('/api/v1/runs/observation-workspace'),
  getAnomalyWorkspace: () => request('/api/v1/runs/anomaly-workspace'),
  getBaselineProfile: () => request('/api/v1/runs/baseline-profile'),
  getInitialization: () => request('/api/v1/runs/initialization'),
  getObjectsSummary: (objectType: string) => request(withQuery('/api/v1/objects/summary', { object_type: objectType })),
  getObjectsList: (query: Record<string, string | number | undefined>) => request(withQuery('/api/v1/objects/list', query)),
  getObjectDetail: (objectType: string, objectId: string) =>
    request(withQuery('/api/v1/objects/detail', { object_type: objectType, object_id: objectId })),
  getProfileList: (query: Record<string, string | number | undefined>) => request(withQuery('/api/v1/objects/profile-list', query)),
  getCompareOverview: () => request('/api/v1/compare/overview'),
  getCompareDiffs: () => request('/api/v1/compare/diffs'),
  getGovernanceOverview: () => request('/api/v1/governance/overview'),
  getGovernanceFields: () => request('/api/v1/governance/fields'),
  getGovernanceTables: () => request('/api/v1/governance/tables'),
  getGovernanceUsage: (tableName: string) => request(`/api/v1/governance/usage/${encodeURIComponent(tableName)}`),
  getGovernanceMigration: () => request('/api/v1/governance/migration'),
};
