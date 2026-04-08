/**
 * 全局状态与常量。
 */

export const API = `${window.location.origin}/api/v1`;
export const CACHE_NS = 'wy-workbench:v2:';

export const PRIMARY_METRIC_CODES = {
  s0: 'total',
  s4: 'trusted_lac_cnt',
  s6: 'output_rows',
  s30: 'total_bs',
  s31: 'filled_from_bs',
  s33: 'by_cell',
  s41: 'total',
  s50: 'lac_profiles',
  s51: 'bs_profiles',
  s52: 'cell_profiles',
};

export const TABLE_LABELS = {
  raw_records: '原始记录表',
  stats_base_raw: '基础统计表',
  fact_filtered: '合规过滤明细',
  stats_lac: 'LAC统计表',
  dim_lac_trusted: '可信LAC维表',
  dim_cell_stats: 'Cell统计维表',
  dim_bs_trusted: '可信BS维表',
  fact_gps_corrected: 'GPS修正明细',
  compare_gps: 'GPS对比结果',
  fact_signal_filled: '信号补齐明细',
  compare_signal: '信号对比结果',
  detect_anomaly_bs: 'BS异常标记',
  detect_collision: '碰撞不足标记',
  map_cell_bs: 'Cell-BS映射',
  fact_final: '最终回归明细',
  profile_lac: 'LAC画像',
  profile_bs: 'BS画像',
  profile_cell: 'Cell画像',
};

export const SAMPLE_TYPE_LABELS = {
  bs: '基站样本',
  cell: 'Cell样本',
  lac: 'LAC样本',
  record: '记录样本',
};

export const state = {
  steps: [],
  context: null,
  versionHistory: [],
  currentPage: 'overview',
  currentStepId: null,
  fields: null,
  fieldFilters: { search: '', table: '', status: '', step: '' },
  samples: null,
  sampleRunId: null,
  sqlCache: new Map(),
};
