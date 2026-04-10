// rebuild5 核心类型定义

// 生命周期状态
export type LifecycleState = 'waiting' | 'observing' | 'qualified' | 'excellent' | 'dormant' | 'retired'

// 状态颜色映射（冻结，不可更改）
export const STATE_COLORS: Record<LifecycleState, string> = {
  excellent: '#22c55e',  // 绿
  qualified: '#3b82f6',  // 蓝
  observing: '#eab308',  // 黄
  waiting: '#9ca3af',    // 灰
  dormant: '#f97316',    // 橙
  retired: '#ef4444',    // 红
}

export const STATE_LABELS: Record<LifecycleState, string> = {
  excellent: '优秀',
  qualified: '合格',
  observing: '观察',
  waiting: '等待',
  dormant: '休眠',
  retired: '退出',
}

// 位置质量
export type PositionGrade = 'excellent' | 'good' | 'qualified' | 'unqualified'

// 漂移分类
export type DriftPattern = 'insufficient' | 'stable' | 'collision' | 'migration' | 'large_coverage' | 'moderate_drift'

export const DRIFT_LABELS: Record<DriftPattern, string> = {
  insufficient: '证据不足',
  stable: '稳定',
  collision: '碰撞',
  migration: '迁移',
  large_coverage: '大覆盖',
  moderate_drift: '中度漂移',
}

// 运营商
export interface Operator {
  operator_code: string
  operator_cn: string
}

export const OPERATORS: Operator[] = [
  { operator_code: '46000', operator_cn: '中国移动' },
  { operator_code: '46001', operator_cn: '中国联通' },
  { operator_code: '46011', operator_cn: '中国电信' },
]

// 页面状态
export type PageStatus = 'running' | 'completed' | 'verifying' | 'published' | 'reverted'

export const PAGE_STATUS_LABELS: Record<PageStatus, string> = {
  running: '运行中',
  completed: '已完成',
  verifying: '验证中',
  published: '已发布',
  reverted: '已回退',
}

// 版本上下文
export interface VersionContext {
  dataset_key: string
  run_id: string
  snapshot_version: string
  status: PageStatus
  updated_at: string
}

// 路径类型
export type PathType = 'A' | 'B' | 'C'

// 分流统计
export interface RoutingStats {
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

// Cell 画像
export interface CellProfile {
  operator_code: string
  lac: string
  cell_id: string
  bs_id: string
  tech_norm: string
  lifecycle_state: LifecycleState
  position_grade: PositionGrade
  anchor_eligible: boolean
  baseline_eligible: boolean
  independent_obs: number
  distinct_dev_id: number
  gps_valid_count: number
  observed_span_hours: number
  p50_radius_m: number
  p90_radius_m: number
  center_lon: number
  center_lat: number
  active_days: number
  rsrp_avg: number | null
  drift_pattern?: DriftPattern
  is_collision?: boolean
  is_dynamic?: boolean
  is_multi_centroid?: boolean
}

// BS 画像
export interface BSProfile {
  operator_code: string
  lac: string
  bs_id: string
  lifecycle_state: LifecycleState
  anchor_eligible: boolean
  baseline_eligible: boolean
  total_cells: number
  qualified_cells: number
  excellent_cells: number
  center_lon: number
  center_lat: number
  large_spread?: boolean
}

// LAC 画像
export interface LACProfile {
  operator_code: string
  lac: string
  lifecycle_state: LifecycleState
  anchor_eligible: boolean
  total_bs: number
  qualified_bs: number
  qualified_bs_ratio: number
}

// ETL 统计
export interface ETLStats {
  source_count: number
  raw_record_count: number
  parsed_record_count: number
  cleaned_record_count: number
  filled_record_count: number
  clean_pass_rate: number
  field_coverage: Record<string, number>
}

// 清洗规则
export interface CleanRule {
  rule_id: string
  rule_name: string
  description: string
  hit_count: number
  drop_count: number
  pass_rate: number
}

// 补数统计
export interface FillStats {
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

// 快照 diff
export interface SnapshotDiff {
  new_registered: number
  promoted: number
  demoted: number
  unchanged: number
  newly_qualified: number
  newly_excellent: number
  entered_dormant: number
  entered_retired: number
}
