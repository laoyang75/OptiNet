"""TA-based trilateration feasibility study (2026-04-22).

Goal: For stable single-centroid 4G cells with sufficient (gps, TA) samples,
test whether trilateration on the TA-derived distances yields a more accurate
cell location than the median GPS center used by trusted_cell_library.

Method:
  Each observation is (gps_lon, gps_lat, ta).
  Distance estimate: d_obs = ta * 78.125  (LTE TA quantum)
  Solve: argmin_{x*, y*} sum_i (haversine(x*, y*, gps_i) - d_obs_i)^2
  Compare against:
    - Median GPS center (current trusted_cell_library approach)
    - Pre-evaluated trusted lon/lat (from trusted_cell_library batch 5)

Output: per-cell summary + per-point residuals.
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass

import numpy as np
import psycopg
from scipy.optimize import least_squares


DSN = os.environ.get(
    "EVAL_DSN",
    "postgresql://postgres:123456@192.168.200.217:5488/yangca",
)

CANDIDATE_CELLS: list[tuple[str, int, int, str, float, float]] = [
    # (operator_code, lac, cell_id, label, trusted_lon, trusted_lat)
    ("46011", 4322, 28436497,  "best (TA 2-7, n=17)",  116.22182, 39.73394),
    ("46000", 4290, 20945465,  "TA 0-5, n=14",          116.44985, 39.86461),
    ("46000", 4102, 20151070,  "TA 7-24, n=8",          116.16102, 39.92596),
    ("46011", 6158, 107892531, "TA 2-3, n=4",           116.30372, 39.96226),
    ("46000", 4352, 19234867,  "TA 1, n=4",             116.65205, 40.11328),
    ("46000", 4284, 22158786,  "TA all 0, n=31",        116.45862, 39.88969),
]

R_EARTH_M = 6371000.0
TA_TO_METER = 78.125


def haversine_m(lon1, lat1, lon2, lat2):
    """Vectorized haversine distance in meters. Handles scalar + array mix."""
    lon1 = np.radians(np.asarray(lon1, dtype=float))
    lat1 = np.radians(np.asarray(lat1, dtype=float))
    lon2 = np.radians(np.asarray(lon2, dtype=float))
    lat2 = np.radians(np.asarray(lat2, dtype=float))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R_EARTH_M * np.arcsin(np.sqrt(a))


@dataclass
class CellEval:
    cell_id: int
    label: str
    n_pts: int
    trusted_lon: float
    trusted_lat: float
    median_lon: float
    median_lat: float
    tri_lon: float
    tri_lat: float
    tri_status: str
    residual_p50_m: float
    residual_p90_m: float
    dist_median_to_trusted_m: float
    dist_tri_to_trusted_m: float
    dist_tri_to_median_m: float


def fetch_pts(conn, op: str, lac: int, cell_id: int) -> np.ndarray:
    """Returns Nx3 array of (lon, lat, ta_int) for valid cell_infos rows."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lon_raw, lat_raw, timing_advance
            FROM rb5.etl_cleaned
            WHERE operator_code = %s AND lac = %s AND cell_id = %s
              AND tech_norm = '4G' AND cell_origin = 'cell_infos'
              AND gps_valid = true
              AND lon_raw IS NOT NULL AND lat_raw IS NOT NULL
              AND timing_advance >= 0 AND timing_advance < 1000
            """,
            (op, lac, cell_id),
        )
        rows = cur.fetchall()
    return np.array(rows, dtype=float)


def trilaterate(pts: np.ndarray) -> tuple[float, float, str]:
    """Solve nonlinear least squares: minimize sum (haversine(x*, y*, gps_i) - ta_i*78.125)^2.

    pts: Nx3 array (lon, lat, ta)
    Returns (lon*, lat*, status)
    """
    if len(pts) < 3:
        return float("nan"), float("nan"), "too_few_points"

    lons = pts[:, 0]
    lats = pts[:, 1]
    d_obs = pts[:, 2] * TA_TO_METER
    # If TA range is degenerate (all same), trilateration is ill-posed
    if np.ptp(d_obs) < 1e-6:
        return float("nan"), float("nan"), "ta_range_degenerate"

    # initial guess: weighted center, lower TA → higher weight
    weights = 1.0 / (d_obs + 78.0)  # avoid 0 div
    x0 = np.array([
        np.average(lons, weights=weights),
        np.average(lats, weights=weights),
    ])

    def residuals(xy):
        return haversine_m(xy[0], xy[1], lons, lats) - d_obs

    try:
        result = least_squares(residuals, x0, method="lm", max_nfev=200)
        return float(result.x[0]), float(result.x[1]), "ok" if result.success else "lm_failed"
    except Exception as exc:  # noqa: BLE001
        return float("nan"), float("nan"), f"err:{exc}"


def evaluate_cell(conn, op: str, lac: int, cell_id: int, label: str,
                   t_lon: float, t_lat: float) -> CellEval | None:
    pts = fetch_pts(conn, op, lac, cell_id)
    if len(pts) == 0:
        print(f"[skip] cell {cell_id}: no points")
        return None

    median_lon = float(np.median(pts[:, 0]))
    median_lat = float(np.median(pts[:, 1]))

    tri_lon, tri_lat, status = trilaterate(pts)

    if math.isnan(tri_lon):
        residual_p50 = float("nan")
        residual_p90 = float("nan")
        dist_tri_to_trusted = float("nan")
        dist_tri_to_median = float("nan")
    else:
        d_obs = pts[:, 2] * TA_TO_METER
        d_pred = haversine_m(tri_lon, tri_lat, pts[:, 0], pts[:, 1])
        residuals = np.abs(d_pred - d_obs)
        residual_p50 = float(np.percentile(residuals, 50))
        residual_p90 = float(np.percentile(residuals, 90))
        dist_tri_to_trusted = float(haversine_m(tri_lon, tri_lat, t_lon, t_lat))
        dist_tri_to_median = float(haversine_m(tri_lon, tri_lat, median_lon, median_lat))

    dist_median_to_trusted = float(haversine_m(median_lon, median_lat, t_lon, t_lat))

    return CellEval(
        cell_id=cell_id,
        label=label,
        n_pts=len(pts),
        trusted_lon=t_lon,
        trusted_lat=t_lat,
        median_lon=median_lon,
        median_lat=median_lat,
        tri_lon=tri_lon,
        tri_lat=tri_lat,
        tri_status=status,
        residual_p50_m=residual_p50,
        residual_p90_m=residual_p90,
        dist_median_to_trusted_m=dist_median_to_trusted,
        dist_tri_to_trusted_m=dist_tri_to_trusted,
        dist_tri_to_median_m=dist_tri_to_median,
    )


def main():
    results: list[CellEval] = []
    with psycopg.connect(DSN) as conn:
        for op, lac, cell_id, label, t_lon, t_lat in CANDIDATE_CELLS:
            ev = evaluate_cell(conn, op, lac, cell_id, label, t_lon, t_lat)
            if ev is not None:
                results.append(ev)

    if not results:
        print("no results")
        return

    # Tabular print
    cols = ["cell_id", "label", "n", "trilat_status",
            "median->trusted", "trilat->trusted", "trilat->median",
            "resid_p50", "resid_p90"]
    widths = [12, 24, 4, 22, 18, 18, 16, 12, 12]
    header = " ".join(c.ljust(w) for c, w in zip(cols, widths))
    print(header)
    print("-" * len(header))
    for r in results:
        def fmt(v):
            if isinstance(v, float):
                if math.isnan(v):
                    return "n/a"
                return f"{v:.1f}"
            return str(v)
        row = [
            str(r.cell_id), r.label, str(r.n_pts), r.tri_status,
            fmt(r.dist_median_to_trusted_m),
            fmt(r.dist_tri_to_trusted_m),
            fmt(r.dist_tri_to_median_m),
            fmt(r.residual_p50_m),
            fmt(r.residual_p90_m),
        ]
        print(" ".join(c.ljust(w) for c, w in zip(row, widths)))


if __name__ == "__main__":
    main()
