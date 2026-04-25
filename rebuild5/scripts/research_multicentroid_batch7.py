#!/usr/bin/env python3
"""Batch-7 multi-centroid study on the top large-radius cells.

This script is intentionally PostGIS-free for the current research round
because the remote PG17 container does not expose the PostGIS extension yet.
It uses:

1. batch7 trusted_cell_library metadata to select 100 "large area + many obs"
   cells
2. cell_sliding_window raw observations for those cells
3. a lightweight DBSCAN-style clustering implementation in Python/numpy

Outputs:
- rebuild5/docs/fix2/multicentroid_batch7_top100_results.json
- rebuild5/docs/fix2/multicentroid_batch7_top100_report.md
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import psycopg


DEFAULT_DSN = 'postgresql://postgres:123456@192.168.200.217:5488/yangca'
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = REPO_ROOT / 'rebuild5/docs/fix2/multicentroid_batch7_top100_results.json'
DEFAULT_MD = REPO_ROOT / 'rebuild5/docs/fix2/multicentroid_batch7_top100_report.md'


@dataclass(frozen=True)
class CandidateKey:
    operator_code: str | None
    lac: int | None
    bs_id: int | None
    cell_id: int | None
    tech_norm: str | None

    def tuple(self) -> tuple[Any, ...]:
        return (self.operator_code, self.lac, self.bs_id, self.cell_id, self.tech_norm)

    def label(self) -> str:
        return f"{self.operator_code}|{self.lac}|{self.bs_id}|{self.cell_id}|{self.tech_norm or ''}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', default=os.getenv('REBUILD5_PG_DSN', DEFAULT_DSN))
    parser.add_argument('--batch-id', type=int, default=7)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--min-p90-m', type=float, default=800.0)
    parser.add_argument('--primary-eps-m', type=float, default=250.0)
    parser.add_argument('--eps-values', default='150,250,400')
    parser.add_argument('--min-samples', type=int, default=4)
    parser.add_argument('--min-cluster-obs', type=int, default=5)
    parser.add_argument('--min-cluster-share', type=float, default=0.10)
    parser.add_argument('--min-cluster-days', type=int, default=2)
    parser.add_argument('--collision-distance-m', type=float, default=20000.0)
    parser.add_argument('--migration-distance-m', type=float, default=500.0)
    parser.add_argument('--out-json', default=str(DEFAULT_JSON))
    parser.add_argument('--out-md', default=str(DEFAULT_MD))
    return parser.parse_args()


def _fetch_candidates(conn: psycopg.Connection, *, batch_id: int, limit: int, min_p90_m: float) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                    operator_code,
                    lac,
                    bs_id,
                    cell_id,
                    tech_norm,
                    p90_radius_m,
                    p50_radius_m,
                    window_obs_count,
                    active_days,
                    distinct_dev_id,
                    drift_pattern,
                    gps_anomaly_type,
                    is_multi_centroid,
                    is_dynamic,
                    ROW_NUMBER() OVER (
                        ORDER BY p90_radius_m DESC NULLS LAST,
                                 window_obs_count DESC,
                                 distinct_dev_id DESC,
                                 active_days DESC,
                                 cell_id
                    ) AS rn
                FROM rb5.trusted_cell_library
                WHERE batch_id = %s
                  AND COALESCE(p90_radius_m, 0) >= %s
            )
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                p90_radius_m,
                p50_radius_m,
                window_obs_count,
                active_days,
                distinct_dev_id,
                drift_pattern,
                gps_anomaly_type,
                is_multi_centroid,
                is_dynamic,
                rn
            FROM ranked
            WHERE rn <= %s
            ORDER BY rn
            """,
            (batch_id, min_p90_m, limit),
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_observations(
    conn: psycopg.Connection,
    *,
    candidates: list[dict[str, Any]],
) -> dict[CandidateKey, list[dict[str, Any]]]:
    if not candidates:
        return {}

    where_parts: list[str] = []
    params: list[Any] = []
    for row in candidates:
        where_parts.append(
            """
            (
                operator_code IS NOT DISTINCT FROM %s
                AND lac IS NOT DISTINCT FROM %s
                AND bs_id IS NOT DISTINCT FROM %s
                AND cell_id IS NOT DISTINCT FROM %s
                AND tech_norm IS NOT DISTINCT FROM %s
            )
            """
        )
        params.extend([
            row['operator_code'],
            row['lac'],
            row['bs_id'],
            row['cell_id'],
            row['tech_norm'],
        ])

    sql = f"""
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            source_row_uid,
            dev_id,
            event_time_std,
            lon_final,
            lat_final,
            gps_valid
        FROM rb5.cell_sliding_window
        WHERE lon_final IS NOT NULL
          AND lat_final IS NOT NULL
          AND ({' OR '.join(where_parts)})
        ORDER BY operator_code, lac, bs_id, cell_id, tech_norm, event_time_std
    """
    grouped: dict[CandidateKey, list[dict[str, Any]]] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        cols = [d.name for d in cur.description]
        for raw in cur.fetchall():
            row = dict(zip(cols, raw))
            key = CandidateKey(
                row['operator_code'],
                row['lac'],
                row['bs_id'],
                row['cell_id'],
                row['tech_norm'],
            )
            grouped[key].append(row)
    return grouped


def _project_points(points: list[dict[str, Any]]) -> np.ndarray:
    lons = np.array([float(p['lon_final']) for p in points], dtype=float)
    lats = np.array([float(p['lat_final']) for p in points], dtype=float)
    lon0 = float(np.median(lons))
    lat0 = float(np.median(lats))
    scale_x = 111000.0 * math.cos(math.radians(lat0))
    xs = (lons - lon0) * scale_x
    ys = (lats - lat0) * 111000.0
    return np.column_stack((xs, ys))


def _dbscan(points_xy: np.ndarray, *, eps_m: float, min_samples: int) -> list[int]:
    n = len(points_xy)
    if n == 0:
        return []
    if n == 1:
        return [0]

    diff = points_xy[:, None, :] - points_xy[None, :, :]
    dist_sq = np.sum(diff * diff, axis=2)
    eps_sq = eps_m * eps_m
    neighbors = [np.flatnonzero(dist_sq[i] <= eps_sq).tolist() for i in range(n)]
    core = [len(nei) >= min_samples for nei in neighbors]

    labels = [-1] * n
    cluster_id = 0
    for idx in range(n):
        if labels[idx] != -1 or not core[idx]:
            continue
        queue = [idx]
        labels[idx] = cluster_id
        while queue:
            current = queue.pop()
            for nb in neighbors[current]:
                if labels[nb] == -1:
                    labels[nb] = cluster_id
                    if core[nb]:
                        queue.append(nb)
        cluster_id += 1

    # Treat isolated noise as its own singleton pseudo-cluster so the report can
    # still account for them deterministically.
    next_cluster = cluster_id
    for idx, label in enumerate(labels):
        if label == -1:
            labels[idx] = next_cluster
            next_cluster += 1
    return labels


def _cluster_stats(
    points: list[dict[str, Any]],
    labels: list[int],
    *,
    min_cluster_obs: int,
    min_cluster_share: float,
    min_cluster_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total_obs = len(points)
    total_devs = len({p['dev_id'] for p in points if p['dev_id'] is not None})
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for point, label in zip(points, labels):
        groups[label].append(point)

    stats: list[dict[str, Any]] = []
    for label, cluster_points in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
        xs = _project_points(cluster_points)
        center = xs.mean(axis=0)
        dists = np.sqrt(np.sum((xs - center) ** 2, axis=1))
        lons = np.array([float(p['lon_final']) for p in cluster_points], dtype=float)
        lats = np.array([float(p['lat_final']) for p in cluster_points], dtype=float)
        dev_count = len({p['dev_id'] for p in cluster_points if p['dev_id'] is not None})
        day_set = {str(p['event_time_std'])[:10] for p in cluster_points if p['event_time_std'] is not None}
        obs_count = len(cluster_points)
        share_ratio = obs_count / total_obs if total_obs else 0.0
        stats.append(
            {
                'cluster_id': int(label),
                'center_lon': float(np.mean(lons)),
                'center_lat': float(np.mean(lats)),
                'obs_count': obs_count,
                'dev_count': dev_count,
                'active_days': len(day_set),
                'share_ratio': share_ratio,
                'radius_m': float(np.max(dists)) if len(dists) else 0.0,
                'first_seen': min(str(p['event_time_std']) for p in cluster_points if p['event_time_std'] is not None),
                'last_seen': max(str(p['event_time_std']) for p in cluster_points if p['event_time_std'] is not None),
                'days': sorted(day_set),
            }
        )

    stable: list[dict[str, Any]] = []
    min_obs_threshold = max(min_cluster_obs, math.ceil(total_obs * min_cluster_share))
    min_dev_threshold = 1 if total_devs <= 2 else 2
    for item in stats:
        if (
            item['obs_count'] >= min_obs_threshold
            and item['dev_count'] >= min_dev_threshold
            and item['active_days'] >= min_cluster_days
        ):
            stable.append(item)
    return stats, stable


def _pairwise_cluster_distances(stable_clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for i in range(len(stable_clusters)):
        for j in range(i + 1, len(stable_clusters)):
            a = stable_clusters[i]
            b = stable_clusters[j]
            lat0 = (a['center_lat'] + b['center_lat']) / 2.0
            scale_x = 111000.0 * math.cos(math.radians(lat0))
            dist = math.sqrt(
                ((a['center_lon'] - b['center_lon']) * scale_x) ** 2
                + ((a['center_lat'] - b['center_lat']) * 111000.0) ** 2
            )
            overlap_days = len(set(a['days']) & set(b['days']))
            pairs.append(
                {
                    'a': a['cluster_id'],
                    'b': b['cluster_id'],
                    'distance_m': dist,
                    'overlap_days': overlap_days,
                }
            )
    return pairs


def _classify_cell(
    stable_clusters: list[dict[str, Any]],
    pairwise: list[dict[str, Any]],
    *,
    collision_distance_m: float,
    migration_distance_m: float,
) -> str:
    if len(stable_clusters) <= 1:
        return 'single_large_coverage'

    max_dist = max((pair['distance_m'] for pair in pairwise), default=0.0)
    if max_dist >= collision_distance_m:
        return 'collision_like'

    if len(stable_clusters) >= 3:
        return 'dynamic_multi'

    primary, secondary = stable_clusters[:2]
    overlap_days = len(set(primary['days']) & set(secondary['days']))
    if (
        max_dist >= migration_distance_m
        and overlap_days <= 1
        and primary['last_seen'] > secondary['last_seen']
    ) or (
        max_dist >= migration_distance_m
        and overlap_days <= 1
        and secondary['last_seen'] > primary['last_seen']
    ):
        return 'migration_like'

    return 'dual_centroid'


def _analyze_candidate(
    meta: dict[str, Any],
    points: list[dict[str, Any]],
    *,
    eps_m: float,
    min_samples: int,
    min_cluster_obs: int,
    min_cluster_share: float,
    min_cluster_days: int,
    collision_distance_m: float,
    migration_distance_m: float,
) -> dict[str, Any]:
    xy = _project_points(points)
    labels = _dbscan(xy, eps_m=eps_m, min_samples=min_samples)
    clusters, stable_clusters = _cluster_stats(
        points,
        labels,
        min_cluster_obs=min_cluster_obs,
        min_cluster_share=min_cluster_share,
        min_cluster_days=min_cluster_days,
    )
    pairwise = _pairwise_cluster_distances(stable_clusters)
    classification = _classify_cell(
        stable_clusters,
        pairwise,
        collision_distance_m=collision_distance_m,
        migration_distance_m=migration_distance_m,
    )
    return {
        'candidate': meta,
        'observation_count': len(points),
        'cluster_count_all': len(clusters),
        'cluster_count_stable': len(stable_clusters),
        'clusters': clusters,
        'stable_clusters': stable_clusters,
        'pairwise_distances': pairwise,
        'research_class': classification,
        'current_flags': {
            'drift_pattern': meta['drift_pattern'],
            'gps_anomaly_type': meta['gps_anomaly_type'],
            'is_multi_centroid': bool(meta['is_multi_centroid']),
            'is_dynamic': bool(meta['is_dynamic']),
        },
    }


def _run_analysis(
    candidates: list[dict[str, Any]],
    observations: dict[CandidateKey, list[dict[str, Any]]],
    *,
    eps_m: float,
    min_samples: int,
    min_cluster_obs: int,
    min_cluster_share: float,
    min_cluster_days: int,
    collision_distance_m: float,
    migration_distance_m: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for meta in candidates:
        key = CandidateKey(
            meta['operator_code'],
            meta['lac'],
            meta['bs_id'],
            meta['cell_id'],
            meta['tech_norm'],
        )
        points = observations.get(key, [])
        if not points:
            continue
        results.append(
            _analyze_candidate(
                meta,
                points,
                eps_m=eps_m,
                min_samples=min_samples,
                min_cluster_obs=min_cluster_obs,
                min_cluster_share=min_cluster_share,
                min_cluster_days=min_cluster_days,
                collision_distance_m=collision_distance_m,
                migration_distance_m=migration_distance_m,
            )
        )
    return results


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    cls_counter = Counter(item['research_class'] for item in results)
    current_multi = sum(1 for item in results if item['current_flags']['is_multi_centroid'])
    current_dynamic = sum(1 for item in results if item['current_flags']['is_dynamic'])
    research_multi = sum(1 for item in results if item['cluster_count_stable'] >= 2)
    research_dynamic = sum(1 for item in results if item['research_class'] == 'dynamic_multi')
    distance_values = [
        pair['distance_m']
        for item in results
        for pair in item['pairwise_distances']
    ]
    return {
        'candidate_count': len(results),
        'research_class_distribution': dict(cls_counter),
        'current_multi_centroid_count': current_multi,
        'current_dynamic_count': current_dynamic,
        'research_multi_centroid_count': research_multi,
        'research_dynamic_count': research_dynamic,
        'max_pair_distance_m': max(distance_values) if distance_values else 0.0,
        'avg_pair_distance_m': sum(distance_values) / len(distance_values) if distance_values else 0.0,
    }


def _sensitivity_summary(
    candidates: list[dict[str, Any]],
    observations: dict[CandidateKey, list[dict[str, Any]]],
    *,
    eps_values: list[float],
    min_samples: int,
    min_cluster_obs: int,
    min_cluster_share: float,
    min_cluster_days: int,
    collision_distance_m: float,
    migration_distance_m: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for eps_m in eps_values:
        analysis = _run_analysis(
            candidates,
            observations,
            eps_m=eps_m,
            min_samples=min_samples,
            min_cluster_obs=min_cluster_obs,
            min_cluster_share=min_cluster_share,
            min_cluster_days=min_cluster_days,
            collision_distance_m=collision_distance_m,
            migration_distance_m=migration_distance_m,
        )
        result[str(int(eps_m))] = _summarize(analysis)
    return result


def _top_examples(results: list[dict[str, Any]], cls_name: str, limit: int = 5) -> list[dict[str, Any]]:
    filtered = [item for item in results if item['research_class'] == cls_name]
    filtered.sort(
        key=lambda item: (
            -float(item['candidate']['p90_radius_m'] or 0.0),
            -int(item['candidate']['window_obs_count'] or 0),
        )
    )
    return filtered[:limit]


def _write_report(
    *,
    out_md: Path,
    generated_at: str,
    settings: dict[str, Any],
    candidates: list[dict[str, Any]],
    observations: dict[CandidateKey, list[dict[str, Any]]],
    primary_results: list[dict[str, Any]],
    primary_summary: dict[str, Any],
    sensitivity: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append('# Batch7 多质心研究报告')
    lines.append('')
    lines.append(f'- 生成时间: `{generated_at}`')
    lines.append(f"- 研究输入数据库: `{settings['dsn']}`")
    lines.append(f"- 研究批次: `batch_id={settings['batch_id']}`")
    lines.append('- 说明: 当前远程 PG17 实例未提供 PostGIS 扩展，本轮研究使用 Python + numpy 对 100 个候选 Cell 做离线聚类验证；后续正式入库实现再迁移到 PostGIS。')
    lines.append('')
    lines.append('## 样本选择')
    lines.append('')
    lines.append(f"- 候选范围: `trusted_cell_library(batch{settings['batch_id']})` 中 `p90_radius_m >= {settings['min_p90_m']}`")
    lines.append(f"- 选样规则: 按 `p90_radius_m DESC, window_obs_count DESC, distinct_dev_id DESC` 取前 `{settings['limit']}` 个 Cell")
    lines.append(f"- 样本总窗口点数: `{sum(len(v) for v in observations.values())}`")
    if candidates:
        obs_values = [int(item['window_obs_count']) for item in candidates]
        lines.append(f"- 样本 `window_obs_count` 范围: `{min(obs_values)} ~ {max(obs_values)}`，均值 `{sum(obs_values)/len(obs_values):.2f}`")
    lines.append('')
    lines.append('## 算法')
    lines.append('')
    lines.append(f"- 主算法: 自定义 DBSCAN 风格密度聚类，`eps={settings['primary_eps_m']}m`, `min_samples={settings['min_samples']}`")
    lines.append(f"- 稳定簇规则: `obs_count >= max({settings['min_cluster_obs']}, total_obs*{settings['min_cluster_share']})` 且 `active_days >= {settings['min_cluster_days']}`")
    lines.append(f"- 分类阈值: `collision_distance >= {settings['collision_distance_m']}m`, `migration_distance >= {settings['migration_distance_m']}m`")
    lines.append('')
    lines.append('## 研究结论')
    lines.append('')
    for key, value in primary_summary['research_class_distribution'].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append(f"- 当前系统 `is_multi_centroid=true` 数: `{primary_summary['current_multi_centroid_count']}`")
    lines.append(f"- 研究判定 `stable_cluster>=2` 数: `{primary_summary['research_multi_centroid_count']}`")
    lines.append(f"- 当前系统 `is_dynamic=true` 数: `{primary_summary['current_dynamic_count']}`")
    lines.append(f"- 研究判定 `dynamic_multi` 数: `{primary_summary['research_dynamic_count']}`")
    lines.append(f"- 稳定簇对最大质心间距: `{primary_summary['max_pair_distance_m']:.1f}m`")
    lines.append(f"- 稳定簇对平均质心间距: `{primary_summary['avg_pair_distance_m']:.1f}m`")
    lines.append('')
    lines.append('## 参数敏感性')
    lines.append('')
    for eps, summary in sensitivity.items():
        dist = summary['research_class_distribution']
        lines.append(
            f"- `eps={eps}m`: "
            f"single=`{dist.get('single_large_coverage', 0)}`, "
            f"dual=`{dist.get('dual_centroid', 0)}`, "
            f"migration=`{dist.get('migration_like', 0)}`, "
            f"dynamic=`{dist.get('dynamic_multi', 0)}`, "
            f"collision=`{dist.get('collision_like', 0)}`"
        )
    lines.append('')
    lines.append('## 观察')
    lines.append('')
    lines.append('- 当前生产标签对“大半径 Cell”明显偏保守：前 100 个研究样本中，系统几乎都已打 `is_multi_centroid=true`，但研究后可拆出更细的 `dual_centroid / migration_like / dynamic_multi / collision_like`。')
    lines.append('- 真正的热点不是“是否存在多簇”，而是“多簇之间的距离 + 时间重叠关系”。这决定了它更像双质心、迁移还是碰撞。')
    lines.append('- `window_obs_count` 和 `active_days` 很多样本都不高，说明未来正式方案必须先做候选集收缩，不能对全量 Cell 逐个做重聚类。')
    lines.append('')
    lines.append('## 代表样本')
    lines.append('')
    for cls_name in ('dual_centroid', 'migration_like', 'dynamic_multi', 'collision_like'):
        examples = _top_examples(primary_results, cls_name)
        if not examples:
            continue
        lines.append(f"### {cls_name}")
        lines.append('')
        for item in examples:
            candidate = item['candidate']
            stable = item['stable_clusters']
            pair_text = ', '.join(
                f"{pair['a']}-{pair['b']}={pair['distance_m']:.0f}m/overlap{pair['overlap_days']}d"
                for pair in item['pairwise_distances']
            ) or 'single'
            lines.append(
                f"- `{candidate['operator_code']}|{candidate['lac']}|{candidate['bs_id']}|{candidate['cell_id']}|{candidate['tech_norm']}` "
                f"`p90={float(candidate['p90_radius_m']):.1f}m`, "
                f"`window_obs={candidate['window_obs_count']}`, "
                f"`stable_clusters={len(stable)}`, "
                f"`pairwise={pair_text}`, "
                f"`current=({candidate['drift_pattern']}, multi={candidate['is_multi_centroid']}, dynamic={candidate['is_dynamic']})`"
            )
        lines.append('')
    lines.append('## 面向 PostGIS 的落地建议')
    lines.append('')
    lines.append('- 远程容器当前没有 `postgis` 扩展；正式入库前，优先在 PG17 容器中补 `postgis`，然后把本脚本的候选集筛选逻辑迁移成 SQL。')
    lines.append('- 推荐的 PG 内实现入口不是全量 Cell，而是 `trusted_cell_library(batch_id=t) WHERE p90_radius_m >= 800 OR gps_anomaly_type IS NOT NULL OR is_dynamic OR is_collision`。')
    lines.append('- 聚类建议优先试 `ST_ClusterDBSCAN`，再把簇结果写回 `cell_centroid_detail`，后续标签在 publish 层判定。')
    lines.append('- 未来线上增量化策略: 只重算 `p90_radius_m`/`gps_anomaly_type`/`drift_pattern` 发生变化的 Cell，历史稳定 Cell 直接复用上轮簇结果。')
    out_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    args = _parse_args()
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    eps_values = [float(v) for v in args.eps_values.split(',') if v.strip()]
    with psycopg.connect(args.dsn) as conn:
        candidates = _fetch_candidates(
            conn,
            batch_id=args.batch_id,
            limit=args.limit,
            min_p90_m=args.min_p90_m,
        )
        observations = _fetch_observations(conn, candidates=candidates)

    primary_results = _run_analysis(
        candidates,
        observations,
        eps_m=args.primary_eps_m,
        min_samples=args.min_samples,
        min_cluster_obs=args.min_cluster_obs,
        min_cluster_share=args.min_cluster_share,
        min_cluster_days=args.min_cluster_days,
        collision_distance_m=args.collision_distance_m,
        migration_distance_m=args.migration_distance_m,
    )
    primary_summary = _summarize(primary_results)
    sensitivity = _sensitivity_summary(
        candidates,
        observations,
        eps_values=eps_values,
        min_samples=args.min_samples,
        min_cluster_obs=args.min_cluster_obs,
        min_cluster_share=args.min_cluster_share,
        min_cluster_days=args.min_cluster_days,
        collision_distance_m=args.collision_distance_m,
        migration_distance_m=args.migration_distance_m,
    )

    payload = {
        'generated_at': datetime.now().isoformat(),
        'settings': {
            'dsn': args.dsn,
            'batch_id': args.batch_id,
            'limit': args.limit,
            'min_p90_m': args.min_p90_m,
            'primary_eps_m': args.primary_eps_m,
            'eps_values': eps_values,
            'min_samples': args.min_samples,
            'min_cluster_obs': args.min_cluster_obs,
            'min_cluster_share': args.min_cluster_share,
            'min_cluster_days': args.min_cluster_days,
            'collision_distance_m': args.collision_distance_m,
            'migration_distance_m': args.migration_distance_m,
        },
        'primary_summary': primary_summary,
        'sensitivity': sensitivity,
        'results': primary_results,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    _write_report(
        out_md=out_md,
        generated_at=payload['generated_at'],
        settings=payload['settings'],
        candidates=candidates,
        observations=observations,
        primary_results=primary_results,
        primary_summary=primary_summary,
        sensitivity=sensitivity,
    )
    print(json.dumps({'out_json': str(out_json), 'out_md': str(out_md), 'summary': primary_summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
