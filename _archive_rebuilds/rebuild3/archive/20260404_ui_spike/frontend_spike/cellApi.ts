export type MetricItem = {
  label: string;
  count: number;
};

export type ChangeItem = {
  label: string;
  effect: string;
  impact_metric: string;
  source_ref: string;
};

export type ScopeItem = {
  label: string;
  value: string;
  detail: string;
  source_ref: string;
};

export type StageItem = {
  stage: string;
  summary: string;
  purpose: string;
  source_ref: string;
};

export type GuardrailItem = {
  label: string;
  value: number;
  detail: string;
};

export type TransparencyResponse = {
  status: string;
  generated_at: string;
  data_origin: string;
  error_message: string | null;
  headline: {
    title: string;
    subtitle: string;
  };
  change_log: ChangeItem[];
  source_scope: ScopeItem[];
  cell_stages: StageItem[];
  legacy_rule: {
    label: string;
    summary: string;
    source_ref: string;
  };
  impact: {
    baseline_delta: number;
    tech_split: MetricItem[];
    reason_split: MetricItem[];
    p90_split: MetricItem[];
    active_days_split: MetricItem[];
    beijing_bbox: {
      inside: number;
      outside: number;
    };
  };
  bs_guardrails: GuardrailItem[];
  notes: string[];
};

export type SummaryResponse = {
  status: string;
  generated_at: string;
  total_objects: number;
  watch_count: number;
  baseline_enabled: number;
  anchorable_enabled: number;
  compare_membership: MetricItem[];
  lifecycle: MetricItem[];
  health: MetricItem[];
  qualification: MetricItem[];
};

export type CellListRow = {
  object_id: string;
  operator_code: string;
  operator_name: string;
  tech_norm: string;
  lac: string;
  bs_id: number;
  cell_id: number;
  lifecycle_state: string;
  health_state: string;
  anchorable: boolean;
  baseline_eligible: boolean;
  record_count: number;
  device_count: number;
  active_days: number;
  gps_p90_dist_m: number;
  gps_original_ratio: number;
  signal_original_ratio: number;
  rsrp_avg: number | null;
  legacy_bs_classification: string | null;
  legacy_gps_quality: string;
  legacy_gps_anomaly: boolean;
  legacy_gps_anomaly_reason: string | null;
  compare_membership: string;
  outside_beijing_bbox: boolean;
  watch: boolean;
};

export type CellListFilters = {
  query?: string;
  operator_code?: string;
  tech_norm?: string;
  lifecycle_state?: string;
  health_state?: string;
  qualification?: string;
  membership?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_dir?: string;
};

export type CellListResponse = {
  status: string;
  generated_at: string;
  rows: CellListRow[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  sort_by: string;
  sort_dir: string;
};

export type FactRouteItem = {
  route: string;
  count: number;
};

export type HistoryItem = {
  changed_at: string;
  changed_reason: string;
  lifecycle_state: string;
  health_state: string;
  anchorable: boolean;
  baseline_eligible: boolean;
};

export type RuleAuditItem = {
  label: string;
  state: string;
  detail: string;
};

export type QualificationReasonItem = {
  label: string;
  passed: boolean;
  items: string[];
};

export type DownstreamItem = {
  bs_object_id: string;
  bs_health_state?: string;
  bs_active_cell_count: number;
  sibling_cell_count?: number;
  sibling_active_cell_count?: number;
  sibling_baseline_cell_count?: number;
  lac_object_id: string;
  lac_health_state?: string;
  lac_active_bs_count: number;
};

export type AnomalyItem = {
  type: string;
  severity: string;
  detail: string;
};

export type CompareContext = {
  membership: string;
  r2_health_state: string;
  r3_health_state: string;
  r2_baseline_eligible: boolean;
  r3_baseline_eligible: boolean;
  legacy_gps_anomaly: boolean;
  legacy_gps_anomaly_reason: string | null;
  explanation: string;
};

export type CellSnapshot = CellListRow & {
  gps_anomaly?: boolean;
  gps_anomaly_reason?: string | null;
  r2_health_state: string;
  r2_baseline_eligible: boolean;
  baseline_center_lon: number | null;
  baseline_center_lat: number | null;
  center_shift_m: number | null;
  bs_object_id: string;
  lac_object_id: string;
  bs_health_state: string;
  lac_health_state: string;
  run_id: string;
  batch_id: string;
  gps_count: number;
  centroid_lon: number | null;
  centroid_lat: number | null;
  gps_p50_dist_m: number | null;
  baseline_gps_p50_dist_m?: number | null;
  baseline_gps_p90_dist_m?: number | null;
  outside_china_bbox?: boolean;
};

export type CellDetailResponse = {
  status: string;
  generated_at: string;
  snapshot: CellSnapshot;
  facts: FactRouteItem[];
  history: HistoryItem[];
  gps_source_mix: MetricItem[];
  signal_source_mix: MetricItem[];
  rule_audit: RuleAuditItem[];
  qualification_reasons: QualificationReasonItem[];
  downstream: DownstreamItem;
  anomalies: AnomalyItem[];
  compare_context: CompareContext;
  change_log: ChangeItem[];
};

export type CellProfileResponse = {
  status: string;
  generated_at: string;
  snapshot: CellSnapshot;
  gps_source_mix: MetricItem[];
  signal_source_mix: MetricItem[];
  facts: FactRouteItem[];
  rule_audit: RuleAuditItem[];
  compare_context: CompareContext;
  profile_notes: string[];
};

const FALLBACK_TRANSPARENCY: TransparencyResponse = {
  status: 'snapshot',
  generated_at: 'frontend fallback',
  data_origin: 'snapshot',
  error_message: '当前未连接后端，页面使用本地快照，但规则可见性仍完整保留。',
  headline: {
    title: 'Cell 规则可见性',
    subtitle: '把研究期过滤、Cell 资格门槛、legacy 差异和 BS 级联修复直接嵌进 Cell 页面。',
  },
  change_log: [
    {
      label: 'Cell baseline 不再直接继承 legacy gps_anomaly 前置硬门槛',
      effect: '当前全量对比里，新增 baseline Cell 为 2,274 个。',
      impact_metric: '+2274 Cell',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:287',
    },
    {
      label: '北京 bbox 没有在 rebuild3 Cell 基线资格里写成长期硬规则',
      effect: '当前新增 baseline Cell 里，只有 2 个落在北京研究框外。',
      impact_metric: '框外 2 个',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:114',
    },
    {
      label: '2G / 3G 没有在 rebuild3 Cell 对象构建阶段显式写死过滤',
      effect: '但本次 baseline 增量实测只出现 4G / 5G，没有 2G / 3G。',
      impact_metric: '2G/3G 增量 0',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:147',
    },
    {
      label: 'BS 资格改成严格来源于子 Cell',
      effect: '修复了“无合格子 Cell 的 BS 仍被判可用”的结构性错误。',
      impact_metric: '异常归零',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:342',
    },
  ],
  source_scope: [
    {
      label: '研究期源表',
      value: '仍是北京一周 GPS / LAC 明细表',
      detail: '当前 rebuild2 输入源表本身就是北京窗口，rebuild3 复用这套输入。',
      source_ref: 'rebuild2/sql/exec_l0_gps.sql:19',
    },
    {
      label: 'GPS 参与计算范围',
      value: '中国 bbox: 73<=lon<=135, 3<=lat<=54',
      detail: '当前 rebuild3 用中国范围做 GPS 合法性与距离统计，不是北京 bbox 硬过滤。',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:114',
    },
    {
      label: '北京 bbox 硬过滤',
      value: '未在 Cell baseline 资格里显式启用',
      detail: '研究期北京约束目前主要体现在源表窗口，而不是 Cell baseline SQL 本身。',
      source_ref: 'docs/rebuild3/01_rebuild3_说明_最终冻结版.md:441',
    },
    {
      label: '2G / 3G 显式过滤',
      value: '未在 rebuild3 Cell 构建 SQL 中写死',
      detail: '但本次新增 baseline Cell 实际只出现 4G / 5G。',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:147',
    },
  ],
  cell_stages: [
    {
      stage: '存在资格',
      summary: 'record_count >= 5, device_count >= 1, active_days >= 1',
      purpose: '决定 Cell 只是被注册，还是还停留在 waiting / observing。',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:280',
    },
    {
      stage: '锚点资格',
      summary: 'gps_count >= 10, device_count >= 2, active_days >= 1, gps_p90_dist_m <= 1500',
      purpose: '决定 Cell 能否作为可信锚点进入正式治理路径。',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:291',
    },
    {
      stage: '基线资格',
      summary: 'gps_count >= 20, device_count >= 2, active_days >= 3, signal_original_ratio >= 0.5, gps_p90_dist_m <= 1500',
      purpose: '决定 Cell 能否沉淀到 baseline / profile。',
      source_ref: 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:296',
    },
    {
      stage: 'legacy 比对门槛',
      summary: 'rebuild2 compare 侧仍要求 gps_anomaly = false',
      purpose: '这是当前 Cell baseline 差异的主来源，需要在 UI 上明确告诉用户。',
      source_ref: 'rebuild3/backend/sql/compare/002_prepare_full_compare.sql:167',
    },
  ],
  legacy_rule: {
    label: 'legacy gps_anomaly 定义',
    summary: 'Cell 中心到 BS 中心距离：5G > 1000m 或 non5G > 2000m 即判异常',
    source_ref: 'rebuild2/backend/app/api/enrich.py:823',
  },
  impact: {
    baseline_delta: 2274,
    tech_split: [
      { label: '5G', count: 2170 },
      { label: '4G', count: 104 },
    ],
    reason_split: [
      { label: 'cell_to_bs_dist>1000m(5G)', count: 2170 },
      { label: 'cell_to_bs_dist>2000m(non5G)', count: 104 },
    ],
    p90_split: [
      { label: '<250m', count: 1037 },
      { label: '250-500m', count: 542 },
      { label: '500-1000m', count: 428 },
      { label: '1000-1500m', count: 267 },
    ],
    active_days_split: [
      { label: '7天', count: 1478 },
      { label: '6天', count: 472 },
      { label: '5天', count: 204 },
      { label: '4天', count: 93 },
      { label: '3天', count: 27 },
    ],
    beijing_bbox: {
      inside: 2272,
      outside: 2,
    },
  },
  bs_guardrails: [
    {
      label: 'BS anchorable 但无 anchorable 子 Cell',
      value: 0,
      detail: '修复后不再允许 BS 脱离 Cell 独立拿到 anchorable。',
    },
    {
      label: 'BS baseline_eligible 但无 baseline 子 Cell',
      value: 0,
      detail: '修复后不再允许 BS baseline 独立漂移。',
    },
    {
      label: 'BS active 但无 active 子 Cell',
      value: 0,
      detail: '修复后生命周期状态和子 Cell 保持一致。',
    },
  ],
  notes: [
    '当前 Cell 增量主因不是 2G/3G 泄漏，也不是北京范围漏控，而是旧 gps_anomaly 门槛被替换成对象自身 P90 稳定性门槛。',
    '如果研究期要继续贴近 rebuild2，可把 legacy gps_anomaly 作为 research-mode 可配置开关重新挂到 Cell baseline 资格里。',
    '这些规则应该放在 Cell 页面直接展示，因为 BS / LAC 的可信性都源自 Cell 的状态与资格。',
  ],
};

const FALLBACK_SUMMARY: SummaryResponse = {
  status: 'snapshot',
  generated_at: 'frontend fallback',
  total_objects: 573561,
  watch_count: 43453,
  baseline_enabled: 194952,
  anchorable_enabled: 265299,
  compare_membership: [
    { label: 'aligned', count: 571287 },
    { label: 'r3_only', count: 2274 },
  ],
  lifecycle: [
    { label: 'active', count: 314322 },
    { label: 'observing', count: 112984 },
    { label: 'waiting', count: 146255 },
  ],
  health: [
    { label: 'healthy', count: 495097 },
    { label: 'gps_bias', count: 41843 },
    { label: 'dynamic', count: 18085 },
    { label: 'collision_confirmed', count: 16743 },
    { label: 'collision_suspect', count: 1793 },
  ],
  qualification: [
    { label: 'anchorable', count: 265299 },
    { label: 'baseline_eligible', count: 194952 },
    { label: 'legacy_gps_anomaly', count: 2274 },
  ],
};

const FALLBACK_LIST_ROWS: CellListRow[] = [
  {
    object_id: 'cell|46011|5G|409602|1711509512',
    operator_code: '46011',
    operator_name: '中国电信',
    tech_norm: '5G',
    lac: '409602',
    bs_id: 417849,
    cell_id: 1711509512,
    lifecycle_state: 'active',
    health_state: 'healthy',
    anchorable: true,
    baseline_eligible: true,
    record_count: 186,
    device_count: 8,
    active_days: 7,
    gps_p90_dist_m: 881.95,
    gps_original_ratio: 0.8123,
    signal_original_ratio: 0.9032,
    rsrp_avg: -94.2,
    legacy_bs_classification: null,
    legacy_gps_quality: '高',
    legacy_gps_anomaly: true,
    legacy_gps_anomaly_reason: 'cell_to_bs_dist>1000m(5G)',
    compare_membership: 'r3_only',
    outside_beijing_bbox: false,
    watch: false,
  },
  {
    object_id: 'cell|46000|4G|4264|10894519',
    operator_code: '46000',
    operator_name: '中国移动',
    tech_norm: '4G',
    lac: '4264',
    bs_id: 42556,
    cell_id: 10894519,
    lifecycle_state: 'active',
    health_state: 'healthy',
    anchorable: true,
    baseline_eligible: true,
    record_count: 54,
    device_count: 4,
    active_days: 6,
    gps_p90_dist_m: 1.13,
    gps_original_ratio: 0.9444,
    signal_original_ratio: 0.8889,
    rsrp_avg: -90.8,
    legacy_bs_classification: null,
    legacy_gps_quality: '高',
    legacy_gps_anomaly: true,
    legacy_gps_anomaly_reason: 'cell_to_bs_dist>2000m(non5G)',
    compare_membership: 'r3_only',
    outside_beijing_bbox: true,
    watch: false,
  },
  {
    object_id: 'cell|46000|4G|12525|23732355',
    operator_code: '46000',
    operator_name: '中国移动',
    tech_norm: '4G',
    lac: '12525',
    bs_id: 92615,
    cell_id: 23732355,
    lifecycle_state: 'observing',
    health_state: 'healthy',
    anchorable: false,
    baseline_eligible: false,
    record_count: 8,
    device_count: 1,
    active_days: 2,
    gps_p90_dist_m: 34.2,
    gps_original_ratio: 0.75,
    signal_original_ratio: 0.63,
    rsrp_avg: -96.0,
    legacy_bs_classification: null,
    legacy_gps_quality: '中',
    legacy_gps_anomaly: false,
    legacy_gps_anomaly_reason: null,
    compare_membership: 'aligned',
    outside_beijing_bbox: false,
    watch: false,
  },
];

const FALLBACK_LIST: CellListResponse = {
  status: 'snapshot',
  generated_at: 'frontend fallback',
  rows: FALLBACK_LIST_ROWS,
  page: 1,
  page_size: 10,
  total: FALLBACK_LIST_ROWS.length,
  total_pages: 1,
  sort_by: 'record_count',
  sort_dir: 'desc',
};

const FALLBACK_GPS_MIX: Record<string, MetricItem[]> = {
  'cell|46011|5G|409602|1711509512': [
    { label: 'original', count: 108 },
    { label: 'cell_center', count: 16 },
    { label: 'bs_center', count: 8 },
  ],
  'cell|46000|4G|4264|10894519': [
    { label: 'original', count: 41 },
    { label: 'cell_center', count: 9 },
    { label: 'bs_center', count: 4 },
  ],
  'cell|46000|4G|12525|23732355': [
    { label: 'original', count: 6 },
    { label: 'cell_center', count: 2 },
  ],
};

const FALLBACK_SIGNAL_MIX: Record<string, MetricItem[]> = {
  'cell|46011|5G|409602|1711509512': [
    { label: 'original', count: 119 },
    { label: 'cell_fill', count: 9 },
    { label: 'bs_fill', count: 4 },
  ],
  'cell|46000|4G|4264|10894519': [
    { label: 'original', count: 48 },
    { label: 'cell_fill', count: 4 },
    { label: 'bs_fill', count: 2 },
  ],
  'cell|46000|4G|12525|23732355': [
    { label: 'original', count: 6 },
    { label: 'cell_fill', count: 2 },
  ],
};

const FALLBACK_FACTS: Record<string, FactRouteItem[]> = {
  'cell|46011|5G|409602|1711509512': [
    { route: 'fact_governed', count: 132 },
    { route: 'fact_pending_observation', count: 0 },
    { route: 'fact_pending_issue', count: 0 },
    { route: 'fact_rejected', count: 0 },
  ],
  'cell|46000|4G|4264|10894519': [
    { route: 'fact_governed', count: 48 },
    { route: 'fact_pending_observation', count: 0 },
    { route: 'fact_pending_issue', count: 0 },
    { route: 'fact_rejected', count: 0 },
  ],
  'cell|46000|4G|12525|23732355': [
    { route: 'fact_governed', count: 0 },
    { route: 'fact_pending_observation', count: 8 },
    { route: 'fact_pending_issue', count: 0 },
    { route: 'fact_rejected', count: 0 },
  ],
};

function buildRuleAudit(row: CellSnapshot): RuleAuditItem[] {
  return [
    {
      label: '研究期输入源',
      state: 'applied',
      detail: '当前仍以北京一周 GPS / LAC 明细表作为研究期输入窗口。',
    },
    {
      label: 'GPS 合法性范围',
      state: 'applied',
      detail: '当前使用中国 bbox：73~135 / 3~54。',
    },
    {
      label: '北京 bbox 硬过滤',
      state: 'not_applied',
      detail: '没有写进 Cell baseline 硬门槛；页面必须显式告诉用户这一点。',
    },
    {
      label: '2G / 3G 显式过滤',
      state: 'not_applied',
      detail: `当前对象制式为 ${row.tech_norm}；SQL 没把 2G/3G 写死成过滤条件。`,
    },
    {
      label: 'legacy gps_anomaly',
      state: 'compare_only',
      detail: 'rebuild2 compare 侧仍把 gps_anomaly=false 当成 baseline 前置条件。',
    },
    {
      label: 'Cell P90 1500m 门槛',
      state: row.gps_p90_dist_m <= 1500 ? 'passed' : 'blocked',
      detail: `当前 gps_p90_dist_m=${row.gps_p90_dist_m.toFixed(2)}m。`,
    },
    {
      label: 'Cell 样本量门槛',
      state: row.gps_count >= 20 && row.device_count >= 2 && row.active_days >= 3 ? 'passed' : 'blocked',
      detail: `gps_count=${row.gps_count}, device_count=${row.device_count}, active_days=${row.active_days}。`,
    },
    {
      label: 'Cell 信号原始率门槛',
      state: row.signal_original_ratio >= 0.5 ? 'passed' : 'blocked',
      detail: `signal_original_ratio=${row.signal_original_ratio.toFixed(4)}，当前基线门槛为 >=0.5。`,
    },
    {
      label: '北京框定位检查',
      state: row.outside_beijing_bbox ? 'warning' : 'passed',
      detail: '只做展示，不作为当前 Cell baseline 直接否决条件。',
    },
    {
      label: 'BS 资格级联',
      state: 'applied',
      detail: 'BS 的 anchorable / baseline_eligible 严格来源于子 Cell。',
    },
  ];
}

function buildQualificationReasons(row: CellSnapshot): QualificationReasonItem[] {
  const anchorItems: string[] = [];
  const baselineItems: string[] = [];

  if (row.gps_count < 10) {
    anchorItems.push(`gps_count=${row.gps_count}，未达到锚点门槛 10。`);
  }
  if (row.device_count < 2) {
    anchorItems.push(`device_count=${row.device_count}，未达到锚点门槛 2。`);
  }
  if (row.gps_p90_dist_m > 1500) {
    anchorItems.push(`gps_p90_dist_m=${row.gps_p90_dist_m.toFixed(2)}m，超过 1500m。`);
  }
  if (row.anchorable && anchorItems.length === 0) {
    anchorItems.push('锚点资格已通过：样本量、设备数、活跃天数和 P90 门槛均满足。');
  }
  if (!row.anchorable && anchorItems.length === 0) {
    anchorItems.push('锚点资格未通过，但当前对象没有命中已展开的显式失败项。');
  }

  if (!row.anchorable) {
    baselineItems.push('锚点禁用对象默认不进入 baseline。');
  }
  if (row.gps_count < 20) {
    baselineItems.push(`gps_count=${row.gps_count}，未达到基线门槛 20。`);
  }
  if (row.device_count < 2) {
    baselineItems.push(`device_count=${row.device_count}，未达到基线门槛 2。`);
  }
  if (row.active_days < 3) {
    baselineItems.push(`active_days=${row.active_days}，未达到基线门槛 3 天。`);
  }
  if (row.signal_original_ratio < 0.5) {
    baselineItems.push(`signal_original_ratio=${row.signal_original_ratio.toFixed(4)}，未达到 0.5。`);
  }
  if (row.gps_p90_dist_m > 1500) {
    baselineItems.push(`gps_p90_dist_m=${row.gps_p90_dist_m.toFixed(2)}m，超过 1500m。`);
  }
  if (row.legacy_gps_anomaly) {
    baselineItems.push('legacy 口径仍会把 gps_anomaly=true 当成 compare 侧否决项。');
  }
  if (row.baseline_eligible && row.compare_membership === 'r3_only') {
    baselineItems.push('当前对象属于 r3_only：rebuild3 允许进 baseline，但 rebuild2 compare 侧仍会拦掉。');
  }
  if (row.baseline_eligible && baselineItems.length === 0) {
    baselineItems.push('基线资格已通过：样本量、活跃天数、信号原始率、P90 均满足。');
  }

  return [
    {
      label: '锚点资格',
      passed: row.anchorable,
      items: anchorItems,
    },
    {
      label: '基线资格',
      passed: row.baseline_eligible,
      items: baselineItems,
    },
  ];
}

function buildCompareContext(row: CellSnapshot): CompareContext {
  const explanation =
    row.compare_membership === 'r3_only'
      ? '当前对象在 rebuild3 可进 baseline，但 rebuild2 compare 侧仍因 legacy gps_anomaly 被拦截。'
      : row.compare_membership === 'r2_only'
        ? '当前对象在 rebuild2 compare 侧仍留在 baseline，但 rebuild3 已收紧资格。'
        : '当前对象在 rebuild2 / rebuild3 的 baseline 资格一致。';

  return {
    membership: row.compare_membership,
    r2_health_state: row.r2_health_state,
    r3_health_state: row.health_state,
    r2_baseline_eligible: row.r2_baseline_eligible,
    r3_baseline_eligible: row.baseline_eligible,
    legacy_gps_anomaly: row.legacy_gps_anomaly,
    legacy_gps_anomaly_reason: row.legacy_gps_anomaly_reason,
    explanation,
  };
}

function buildFallbackSnapshot(objectId: string): CellSnapshot {
  const row = FALLBACK_LIST_ROWS.find((item) => item.object_id === objectId) ?? FALLBACK_LIST_ROWS[0];
  const snapshot: CellSnapshot = {
    ...row,
    gps_anomaly: row.legacy_gps_anomaly,
    gps_anomaly_reason: row.legacy_gps_anomaly_reason,
    r2_health_state: row.compare_membership === 'r3_only' ? 'gps_bias' : row.health_state,
    r2_baseline_eligible: row.compare_membership !== 'r3_only',
    baseline_center_lon: 116.4376,
    baseline_center_lat: 39.9213,
    center_shift_m: row.object_id === 'cell|46011|5G|409602|1711509512' ? 23.0 : row.object_id === 'cell|46000|4G|4264|10894519' ? 15.46 : 6.2,
    bs_object_id: `bs|${row.operator_code}|${row.tech_norm}|${row.lac}|${row.bs_id}`,
    lac_object_id: `lac|${row.operator_code}|${row.tech_norm}|${row.lac}`,
    bs_health_state: 'healthy',
    lac_health_state: 'healthy',
    run_id: 'RUN-FULL-20251201-20251207-V1',
    batch_id: 'BATCH-FULL-20251201-20251207-V1',
    gps_count: row.object_id === 'cell|46011|5G|409602|1711509512' ? 142 : row.object_id === 'cell|46000|4G|4264|10894519' ? 43 : 6,
    centroid_lon: row.object_id === 'cell|46011|5G|409602|1711509512' ? 116.43782 : row.object_id === 'cell|46000|4G|4264|10894519' ? 116.40883 : 116.51224,
    centroid_lat: row.object_id === 'cell|46011|5G|409602|1711509512' ? 39.92111 : row.object_id === 'cell|46000|4G|4264|10894519' ? 40.01546 : 39.87344,
    gps_p50_dist_m: row.object_id === 'cell|46011|5G|409602|1711509512' ? 254.3 : row.object_id === 'cell|46000|4G|4264|10894519' ? 0.4 : 18.6,
    baseline_gps_p50_dist_m: row.object_id === 'cell|46011|5G|409602|1711509512' ? 248.8 : row.object_id === 'cell|46000|4G|4264|10894519' ? 0.5 : 17.2,
    baseline_gps_p90_dist_m: row.object_id === 'cell|46011|5G|409602|1711509512' ? 862.1 : row.object_id === 'cell|46000|4G|4264|10894519' ? 0.9 : 29.7,
    outside_china_bbox: false,
  };
  return snapshot;
}

function buildFallbackDetail(objectId: string): CellDetailResponse {
  const snapshot = buildFallbackSnapshot(objectId);
  return {
    status: 'snapshot',
    generated_at: 'frontend fallback',
    snapshot,
    facts: FALLBACK_FACTS[snapshot.object_id] ?? FALLBACK_FACTS[FALLBACK_LIST_ROWS[0].object_id],
    history: [
      {
        changed_at: '2026-04-04T19:46:47+08:00',
        changed_reason: 'full_init_snapshot',
        lifecycle_state: snapshot.lifecycle_state,
        health_state: snapshot.health_state,
        anchorable: snapshot.anchorable,
        baseline_eligible: snapshot.baseline_eligible,
      },
    ],
    gps_source_mix: FALLBACK_GPS_MIX[snapshot.object_id] ?? FALLBACK_GPS_MIX[FALLBACK_LIST_ROWS[0].object_id],
    signal_source_mix: FALLBACK_SIGNAL_MIX[snapshot.object_id] ?? FALLBACK_SIGNAL_MIX[FALLBACK_LIST_ROWS[0].object_id],
    rule_audit: buildRuleAudit(snapshot),
    qualification_reasons: buildQualificationReasons(snapshot),
    downstream: {
      bs_object_id: snapshot.bs_object_id,
      bs_health_state: snapshot.bs_health_state,
      bs_active_cell_count: snapshot.object_id === 'cell|46011|5G|409602|1711509512' ? 4 : 3,
      sibling_cell_count: snapshot.object_id === 'cell|46011|5G|409602|1711509512' ? 6 : 4,
      sibling_active_cell_count: snapshot.object_id === 'cell|46011|5G|409602|1711509512' ? 4 : 2,
      sibling_baseline_cell_count: snapshot.object_id === 'cell|46011|5G|409602|1711509512' ? 3 : 1,
      lac_object_id: snapshot.lac_object_id,
      lac_health_state: snapshot.lac_health_state,
      lac_active_bs_count: snapshot.object_id === 'cell|46011|5G|409602|1711509512' ? 12 : 7,
    },
    anomalies: snapshot.legacy_gps_anomaly
      ? [
          {
            type: 'legacy_gps_anomaly',
            severity: 'compare_only',
            detail: snapshot.legacy_gps_anomaly_reason ?? 'legacy compare 侧命中 gps_anomaly。',
          },
        ]
      : [],
    compare_context: buildCompareContext(snapshot),
    change_log: FALLBACK_TRANSPARENCY.change_log,
  };
}

function buildFallbackProfile(objectId: string): CellProfileResponse {
  const detail = buildFallbackDetail(objectId);
  const notes = [] as string[];
  if (detail.compare_context.membership === 'r3_only') {
    notes.push('该 Cell 属于 r3_only：rebuild3 已允许进入 baseline，但 rebuild2 compare 侧仍会拦截。');
  }
  if (detail.snapshot.legacy_gps_anomaly) {
    notes.push('legacy gps_anomaly 仍被命中，说明旧口径更偏向用 Cell-BS 距离硬阈值。');
  }
  if (detail.snapshot.outside_beijing_bbox) {
    notes.push('当前质心落在北京研究框外；这在 UI 上必须直接可见。');
  }
  return {
    status: 'snapshot',
    generated_at: detail.generated_at,
    snapshot: detail.snapshot,
    gps_source_mix: detail.gps_source_mix,
    signal_source_mix: detail.signal_source_mix,
    facts: detail.facts,
    rule_audit: detail.rule_audit,
    compare_context: detail.compare_context,
    profile_notes: notes,
  };
}

function toQueryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== 'all') {
      search.set(key, String(value));
    }
  });
  const raw = search.toString();
  return raw ? `?${raw}` : '';
}

async function fetchWithFallback<T>(url: string, fallbackFactory: () => T): Promise<T> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (_error) {
    return fallbackFactory();
  }
}

function applyFallbackList(filters: CellListFilters = {}): CellListResponse {
  const page = filters.page ?? 1;
  const pageSize = filters.page_size ?? 10;
  const sortBy = filters.sort_by ?? 'record_count';
  const sortDir = filters.sort_dir ?? 'desc';

  let rows = [...FALLBACK_LIST_ROWS];
  const query = filters.query?.trim().toLowerCase();
  if (query) {
    rows = rows.filter((row) => {
      return [row.object_id, row.lac, String(row.bs_id), String(row.cell_id)].some((value) => value.toLowerCase().includes(query));
    });
  }
  if (filters.operator_code && filters.operator_code !== 'all') {
    rows = rows.filter((row) => row.operator_code === filters.operator_code);
  }
  if (filters.tech_norm && filters.tech_norm !== 'all') {
    rows = rows.filter((row) => row.tech_norm === filters.tech_norm);
  }
  if (filters.lifecycle_state && filters.lifecycle_state !== 'all') {
    rows = rows.filter((row) => row.lifecycle_state === filters.lifecycle_state);
  }
  if (filters.health_state && filters.health_state !== 'all') {
    rows = rows.filter((row) => row.health_state === filters.health_state);
  }
  if (filters.qualification === 'anchorable') {
    rows = rows.filter((row) => row.anchorable);
  }
  if (filters.qualification === 'not_anchorable') {
    rows = rows.filter((row) => !row.anchorable);
  }
  if (filters.qualification === 'baseline') {
    rows = rows.filter((row) => row.baseline_eligible);
  }
  if (filters.qualification === 'not_baseline') {
    rows = rows.filter((row) => !row.baseline_eligible);
  }
  if (filters.membership && filters.membership !== 'all') {
    rows = rows.filter((row) => row.compare_membership === filters.membership);
  }

  rows.sort((left, right) => {
    const a = left[sortBy as keyof CellListRow];
    const b = right[sortBy as keyof CellListRow];
    if (a === b) {
      return left.object_id.localeCompare(right.object_id);
    }
    const order = sortDir === 'asc' ? 1 : -1;
    if (a === null || a === undefined) {
      return 1;
    }
    if (b === null || b === undefined) {
      return -1;
    }
    if (typeof a === 'number' && typeof b === 'number') {
      return (a - b) * order;
    }
    return String(a).localeCompare(String(b), 'zh-CN') * order;
  });

  const total = rows.length;
  const paged = rows.slice((page - 1) * pageSize, page * pageSize);
  return {
    status: 'snapshot',
    generated_at: 'frontend fallback',
    rows: paged,
    page,
    page_size: pageSize,
    total,
    total_pages: Math.max(1, Math.ceil(total / pageSize)),
    sort_by: sortBy,
    sort_dir: sortDir,
  };
}

export async function fetchCellTransparency(): Promise<TransparencyResponse> {
  return fetchWithFallback('/api/v1/objects/cell/transparency', () => FALLBACK_TRANSPARENCY);
}

export async function fetchCellSummary(): Promise<SummaryResponse> {
  return fetchWithFallback('/api/v1/objects/cell/summary', () => FALLBACK_SUMMARY);
}

export async function fetchCellList(filters: CellListFilters = {}): Promise<CellListResponse> {
  const url = `/api/v1/objects/cell/list${toQueryString(filters)}`;
  return fetchWithFallback(url, () => applyFallbackList(filters));
}

export async function fetchCellDetail(objectId: string): Promise<CellDetailResponse> {
  const url = `/api/v1/objects/cell/${encodeURIComponent(objectId)}/detail`;
  return fetchWithFallback(url, () => buildFallbackDetail(objectId));
}

export async function fetchCellProfile(objectId: string): Promise<CellProfileResponse> {
  const url = `/api/v1/objects/cell/${encodeURIComponent(objectId)}/profile`;
  return fetchWithFallback(url, () => buildFallbackProfile(objectId));
}

export const fallbackCellObjectId = FALLBACK_LIST_ROWS[0].object_id;
export const fallbackTransparency = FALLBACK_TRANSPARENCY;
