import type {
  VersionContext, RoutingStats, CellProfile, BSProfile, LACProfile,
  ETLStats, CleanRule, FillStats, SnapshotDiff, LifecycleState
} from '../types'

export const mockVersion: VersionContext = {
  dataset_key: 'sample_6lac',
  run_id: 'run_20260408_001',
  snapshot_version: 'v3',
  status: 'published',
  updated_at: '2026-04-08 18:30:00',
}

export const mockETLStats: ETLStats = {
  source_count: 3,
  raw_record_count: 1_248_350,
  parsed_record_count: 3_872_640,
  cleaned_record_count: 3_156_210,
  filled_record_count: 3_156_210,
  clean_pass_rate: 0.815,
  field_coverage: {
    cell_id: 1.0, lac: 0.98, bs_id: 0.95, operator_code: 0.92,
    lon_raw: 0.68, lat_raw: 0.68, rsrp: 0.73, rsrq: 0.41,
    sinr: 0.39, pressure: 0.12, tech_norm: 0.88,
  },
}

export const mockCleanRules: CleanRule[] = [
  { rule_id: 'R01', rule_name: 'cell_id 为 0 或不可解析', description: '主键无效，整行删除', hit_count: 18420, drop_count: 18420, pass_rate: 0.985 },
  { rule_id: 'R02', rule_name: 'cell_id 溢出', description: 'cell_id 超出合法范围', hit_count: 3210, drop_count: 3210, pass_rate: 0.997 },
  { rule_id: 'R03', rule_name: '经度越界', description: '经度不在 73°~135°', hit_count: 45620, drop_count: 0, pass_rate: 1.0 },
  { rule_id: 'R04', rule_name: '纬度越界', description: '纬度不在 3°~54°', hit_count: 38750, drop_count: 0, pass_rate: 1.0 },
  { rule_id: 'R05', rule_name: 'RSRP 越界', description: 'RSRP 不在 -156~0 dBm', hit_count: 12300, drop_count: 0, pass_rate: 1.0 },
  { rule_id: 'R06', rule_name: '运营商异常', description: '无法映射到已知运营商', hit_count: 8900, drop_count: 0, pass_rate: 1.0 },
  { rule_id: 'R07', rule_name: '非原生 GPS', description: 'WiFi/基站定位数据，非原生 GPS', hit_count: 156200, drop_count: 0, pass_rate: 1.0 },
  { rule_id: 'R08', rule_name: '时间戳异常', description: '事件时间超出数据集范围', hit_count: 5430, drop_count: 5430, pass_rate: 0.996 },
]

export const mockRoutingStats: RoutingStats = {
  input_record_count: 3_156_210,
  path_a_record_count: 1_892_520,
  path_b_record_count: 987_340,
  path_b_cell_count: 4_328,
  path_c_drop_count: 276_350,
  collision_candidate_count: 3_420,
  collision_path_a_match_count: 2_890,
  collision_pending_count: 180,
  collision_drop_count: 350,
}

export const mockSnapshotDiff: SnapshotDiff = {
  new_registered: 312,
  promoted: 186,
  demoted: 23,
  unchanged: 3_807,
  newly_qualified: 142,
  newly_excellent: 44,
  entered_dormant: 18,
  entered_retired: 5,
}

// Cell 分布
export const mockCellStateDistribution: Record<LifecycleState, number> = {
  excellent: 1_245,
  qualified: 2_890,
  observing: 1_560,
  waiting: 980,
  active: 0,
  dormant: 120,
  retired: 45,
}

// BS 分布
export const mockBSStateDistribution: Record<LifecycleState, number> = {
  excellent: 320,
  qualified: 780,
  observing: 450,
  waiting: 280,
  active: 0,
  dormant: 35,
  retired: 12,
}

// LAC 分布（BS-LAC-v1：LAC 用 active/dormant/retired）
export const mockLACStateDistribution: Record<LifecycleState, number> = {
  excellent: 0,
  qualified: 0,
  observing: 0,
  waiting: 0,
  active: 6,
  dormant: 0,
  retired: 0,
}

// 样本 Cell 列表
export const mockCells: CellProfile[] = Array.from({ length: 50 }, (_, i) => {
  const states: LifecycleState[] = ['excellent', 'qualified', 'observing', 'waiting', 'dormant', 'retired']
  const state = states[i % 6]
  return {
    operator_code: ['46000', '46001', '46011'][i % 3],
    lac: `${4000 + Math.floor(i / 10)}`,
    cell_id: `${10000 + i}`,
    bs_id: `${5000 + Math.floor(i / 3)}`,
    tech_norm: i % 4 === 0 ? '5G' : '4G',
    lifecycle_state: state,
    position_grade: state === 'excellent' ? 'excellent' : state === 'qualified' ? 'good' : 'qualified',
    anchor_eligible: state === 'excellent' || state === 'qualified',
    baseline_eligible: state === 'excellent',
    independent_obs: Math.floor(Math.random() * 50) + 1,
    distinct_dev_id: Math.floor(Math.random() * 10) + 1,
    gps_valid_count: Math.floor(Math.random() * 100),
    observed_span_hours: Math.floor(Math.random() * 200),
    p50_radius_m: Math.floor(Math.random() * 800),
    p90_radius_m: Math.floor(Math.random() * 1500),
    center_lon: 116.3 + Math.random() * 0.5,
    center_lat: 39.9 + Math.random() * 0.3,
    active_days: Math.floor(Math.random() * 30),
    rsrp_avg: -(Math.floor(Math.random() * 60) + 70),
    drift_pattern: ['stable', 'collision', 'migration', 'large_coverage', 'stable', 'stable'][i % 6] as any,
    is_collision: i % 12 === 0,
    is_dynamic: i % 15 === 0,
    is_multi_centroid: i % 20 === 0,
  }
})

export const mockBSList: BSProfile[] = Array.from({ length: 20 }, (_, i) => {
  const states: LifecycleState[] = ['excellent', 'qualified', 'observing', 'waiting']
  return {
    operator_code: ['46000', '46001', '46011'][i % 3],
    lac: `${4000 + Math.floor(i / 5)}`,
    bs_id: `${5000 + i}`,
    lifecycle_state: states[i % 4],
    anchor_eligible: i % 4 < 2,
    baseline_eligible: i % 4 === 0,
    total_cells: Math.floor(Math.random() * 10) + 2,
    qualified_cells: Math.floor(Math.random() * 5),
    excellent_cells: Math.floor(Math.random() * 3),
    center_lon: 116.3 + Math.random() * 0.5,
    center_lat: 39.9 + Math.random() * 0.3,
    large_spread: i % 8 === 0,
  }
})

export const mockLACList: LACProfile[] = Array.from({ length: 6 }, (_, i) => ({
  operator_code: ['46000', '46001', '46011'][i % 3],
  lac: `${4000 + i}`,
  lifecycle_state: (['excellent', 'qualified', 'qualified', 'observing', 'qualified', 'qualified'] as LifecycleState[])[i],
  anchor_eligible: i < 5,
  total_bs: Math.floor(Math.random() * 200) + 50,
  qualified_bs: Math.floor(Math.random() * 100) + 10,
  qualified_bs_ratio: Math.random() * 0.5 + 0.3,
}))

export const mockFillStats: FillStats = {
  total_path_a: 1_892_520,
  donor_matched_count: 1_500_000,
  gps_filled: 345_000,
  rsrp_filled: 128_400,
  rsrq_filled: 95_200,
  sinr_filled: 88_600,
  operator_filled: 23_100,
  lac_filled: 12_800,
  tech_filled: 3_200,
  gps_anomaly_count: 4_520,
  collision_skip_anomaly_count: 320,
  donor_excellent_count: 890,
  donor_qualified_count: 1_456,
  remaining_none_gps: 45_000,
  remaining_none_signal: 12_000,
}
