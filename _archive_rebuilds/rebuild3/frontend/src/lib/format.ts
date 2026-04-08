const LIFECYCLE_LABELS: Record<string, string> = {
  waiting: '等待',
  observing: '观察',
  active: '活跃',
  dormant: '休眠',
  retired: '退役',
  rejected: '拒收',
};

const HEALTH_LABELS: Record<string, string> = {
  healthy: '健康',
  insufficient: '数据不足',
  gps_bias: 'GPS 偏差',
  collision_suspect: '碰撞嫌疑',
  collision_confirmed: '碰撞确认',
  dynamic: '动态',
  migration_suspect: '迁移嫌疑',
};

const ROUTE_LABELS: Record<string, string> = {
  fact_governed: '正式治理',
  fact_pending_observation: '待观察',
  fact_pending_issue: '待处理问题',
  fact_rejected: '已拒收',
};

const COMPARE_LABELS: Record<string, string> = {
  aligned: '口径对齐',
  r3_only: '仅 rebuild3',
  r2_only: '仅 rebuild2',
};

export function formatNumber(value: number | string | null | undefined): string {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) return '--';
  return new Intl.NumberFormat('zh-CN').format(numeric);
}

export function formatPercent(value: number | string | null | undefined, digits = 1): string {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) return '--';
  return `${(numeric * 100).toFixed(digits)}%`;
}

export function formatDecimal(value: number | string | null | undefined, digits = 1): string {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) return '--';
  return numeric.toFixed(digits);
}

export function formatMeters(value: number | string | null | undefined, digits = 1): string {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) return '--';
  return `${numeric.toFixed(digits)} m`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '--';
  return value.replace('T', ' ').replace('.000Z', 'Z');
}

export function lifecycleTone(value: string): string {
  return {
    waiting: 'amber',
    observing: 'amber-strong',
    active: 'green',
    dormant: 'slate',
    retired: 'slate-muted',
    rejected: 'red',
  }[value] ?? 'slate';
}

export function lifecycleLabel(value: string | null | undefined): string {
  return LIFECYCLE_LABELS[value ?? ''] ?? value ?? '--';
}

export function healthTone(value: string): string {
  return {
    healthy: 'green',
    insufficient: 'slate',
    gps_bias: 'orange',
    collision_suspect: 'orange',
    collision_confirmed: 'red',
    dynamic: 'blue',
    migration_suspect: 'indigo',
  }[value] ?? 'slate';
}

export function healthLabel(value: string | null | undefined): string {
  return HEALTH_LABELS[value ?? ''] ?? value ?? '--';
}

export function routeTone(value: string): string {
  return {
    fact_governed: 'green',
    fact_pending_observation: 'amber',
    fact_pending_issue: 'orange',
    fact_rejected: 'red',
  }[value] ?? 'slate';
}

export function routeLabel(value: string | null | undefined): string {
  return ROUTE_LABELS[value ?? ''] ?? value ?? '--';
}

export function compareTone(value: string): string {
  return {
    aligned: 'slate',
    r3_only: 'indigo',
    r2_only: 'orange',
  }[value] ?? 'slate';
}

export function compareLabel(value: string | null | undefined): string {
  return COMPARE_LABELS[value ?? ''] ?? value ?? '--';
}

const REGION_QUALITY_LABELS: Record<string, string> = {
  issue_present: '存在问题',
  healthy: '健康',
  insufficient: '数据不足',
  mixed: '混合',
};

export function regionQualityLabel(value: string | null | undefined): string {
  return REGION_QUALITY_LABELS[value ?? ''] ?? value ?? '区域标签未提供';
}

export function objectTypeLabel(value: string): string {
  return {
    cell: 'Cell',
    bs: 'BS',
    lac: 'LAC',
  }[value] ?? value;
}

export function serviceStatusLabel(value: string | null | undefined): string {
  return {
    running: '运行中',
    stopped: '已停止',
    starting: '启动中',
    'process-only': '进程未就绪',
    'port-open': '端口占用',
    error: '错误',
  }[value ?? ''] ?? value ?? '--';
}

export function serviceStatusTone(value: string | null | undefined): string {
  return {
    running: 'green',
    stopped: 'red',
    starting: 'amber',
    'process-only': 'amber',
    'port-open': 'orange',
    error: 'red',
  }[value ?? ''] ?? 'slate';
}

export function severityTone(value: string | null | undefined): string {
  return {
    high: 'red',
    medium: 'orange',
    low: 'amber',
  }[value ?? ''] ?? 'slate';
}

export function severityLabel(value: string | null | undefined): string {
  return {
    high: '高',
    medium: '中',
    low: '低',
  }[value ?? ''] ?? value ?? '--';
}
