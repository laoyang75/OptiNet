export function fmt(n: number): string {
  return n.toLocaleString('zh-CN')
}

export function pct(n: number, digits = 1): string {
  return (n * 100).toFixed(digits) + '%'
}

export function fmtCompact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return n.toString()
}
