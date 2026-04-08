"""Shared context helpers: current pointer, contract/rule versions."""
from .database import fetchone

CONTRACT_VERSION = "rebuild4-final-freeze-2026-04-06-v6"


def get_current_pointer() -> dict | None:
    return fetchone("""
        SELECT cp.pointer_name, cp.current_run_id, cp.current_batch_id,
               cp.pointer_source, cp.switched_at,
               cv.version_label as contract_version,
               rs.version_label as rule_set_version
        FROM rebuild4_meta.current_pointer cp
        JOIN rebuild4_meta.contract_version cv ON cv.version_id = cp.contract_version_id AND cv.is_current = true
        JOIN rebuild4_meta.rule_set_version rs ON rs.is_current = true
        WHERE cp.pointer_name = 'main'
    """)


def get_current_profile_run() -> dict | None:
    """获取当前 profile run 的信息（优先用 run_log，回退到 snapshot 表）。"""
    # 尝试从 run_log 获取
    row = fetchone("""
        SELECT r.profile_run_id, r.snapshot_count,
               r.final_cell_count, r.final_bs_count, r.final_lac_count,
               r.params_hash, r.status, r.started_at, r.finished_at,
               s.snapshot_seq AS latest_seq, s.snapshot_label AS latest_label
        FROM rebuild4_meta.etl_profile_run_log r
        LEFT JOIN rebuild4_meta.etl_profile_snapshot s
          ON s.profile_run_id = r.profile_run_id
         AND s.snapshot_seq = r.snapshot_count
        WHERE r.is_current = true
        LIMIT 1
    """)
    if row:
        return row
    # 回退: run_log 表不存在或为空时，从 snapshot 表推断
    return fetchone("""
        SELECT profile_run_id,
               MAX(snapshot_seq)   AS latest_seq,
               MAX(snapshot_label) AS latest_label,
               COUNT(*)           AS snapshot_count
        FROM rebuild4_meta.etl_profile_snapshot
        GROUP BY profile_run_id
        ORDER BY MAX(created_at) DESC
        LIMIT 1
    """)


def base_context() -> dict:
    cp = get_current_pointer()
    ctx = {}
    if cp:
        ctx["contract_version"] = cp["contract_version"]
        ctx["rule_set_version"] = cp["rule_set_version"]
        ctx["run_id"] = cp["current_run_id"]
        ctx["batch_id"] = cp["current_batch_id"]
    else:
        ctx["contract_version"] = CONTRACT_VERSION

    pr = get_current_profile_run()
    if pr:
        ctx["profile_run_id"] = pr["profile_run_id"]
        ctx["snapshot_seq"] = pr["latest_seq"]
        ctx["snapshot_label"] = pr["latest_label"]
        ctx["snapshot_count"] = pr["snapshot_count"]
        if pr.get("params_hash"):
            ctx["params_hash"] = pr["params_hash"]

    return ctx


def get_current_baseline_version() -> str | None:
    row = fetchone("SELECT baseline_version FROM rebuild4_meta.baseline_version WHERE is_current = true")
    return row["baseline_version"] if row else None
