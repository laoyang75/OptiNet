export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--';
  }
  return new Intl.NumberFormat('zh-CN').format(value);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--';
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMeters(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--';
  }
  return `${value.toFixed(digits)}m`;
}

export function formatCoordinate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--';
  }
  return value.toFixed(6);
}

export function formatSignedNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--';
  }
  const fixed = value % 1 === 0 ? value.toFixed(0) : value.toFixed(1);
  return value > 0 ? `+${fixed}` : fixed;
}

export type BadgeTone = 'blue' | 'green' | 'amber' | 'orange' | 'red' | 'slate' | 'violet';

export function lifecycleTone(state: string): BadgeTone {
  switch (state) {
    case 'active':
      return 'green';
    case 'waiting':
    case 'observing':
      return 'amber';
    case 'dormant':
      return 'slate';
    case 'retired':
      return 'violet';
    case 'rejected':
      return 'red';
    default:
      return 'blue';
  }
}

export function lifecycleLabel(state: string): string {
  const map: Record<string, string> = {
    active: '活跃',
    waiting: '等待中',
    observing: '观察中',
    dormant: '休眠',
    retired: '退役',
    rejected: '拒绝',
  };
  return map[state] ?? state;
}

export function healthTone(state: string): BadgeTone {
  switch (state) {
    case 'healthy':
      return 'green';
    case 'gps_bias':
    case 'dynamic':
    case 'migration_suspect':
      return 'orange';
    case 'collision_confirmed':
      return 'red';
    case 'collision_suspect':
      return 'amber';
    default:
      return 'slate';
  }
}

export function healthLabel(state: string): string {
  const map: Record<string, string> = {
    healthy: '健康',
    gps_bias: 'GPS偏差',
    dynamic: '动态',
    migration_suspect: '迁移嫌疑',
    collision_suspect: '碰撞嫌疑',
    collision_confirmed: '碰撞确认',
    data_insufficient: '数据不足',
  };
  return map[state] ?? state;
}

export function compareTone(membership: string): BadgeTone {
  switch (membership) {
    case 'r3_only':
      return 'orange';
    case 'r2_only':
      return 'red';
    default:
      return 'blue';
  }
}

export function compareLabel(membership: string): string {
  const map: Record<string, string> = {
    aligned: '口径对齐',
    r3_only: '仅 rebuild3',
    r2_only: '仅 rebuild2',
  };
  return map[membership] ?? membership;
}

export function ruleTone(state: string): BadgeTone {
  switch (state) {
    case 'passed':
    case 'applied':
      return 'green';
    case 'warning':
    case 'compare_only':
      return 'amber';
    case 'blocked':
    case 'not_applied':
      return 'orange';
    default:
      return 'slate';
  }
}

export function ruleLabel(state: string): string {
  const map: Record<string, string> = {
    passed: '通过',
    blocked: '未通过',
    applied: '已启用',
    not_applied: '未启用',
    warning: '提示',
    compare_only: '仅 compare',
  };
  return map[state] ?? state;
}
