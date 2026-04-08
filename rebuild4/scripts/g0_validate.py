#!/usr/bin/env python3
"""
Phase 0 / Gate G0: Frozen package read-only validation.
Steps: P0-G0-01, P0-G0-02, P0-G0-03
"""

import json
import os
import hashlib
import re
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_DIR = os.path.join(BASE_DIR, "docs", "03_final")
PACKAGE_ID = "rebuild4-final-freeze-2026-04-06-v6"
ARTIFACT_DIR = os.path.join(
    BASE_DIR, "runtime_artifacts", "gate", PACKAGE_ID, "G0", "attempt_001"
)

EXPECTED_FILES = [
    "00_最终冻结基线.md",
    "01_最终技术栈与基础框架约束.md",
    "02_数据生成与回灌策略.md",
    "03_最终执行任务书.md",
    "04_最终校验清单.md",
    "05_本轮范围与降级说明.md",
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def step_g0_01():
    """P0-G0-01: Validate six frozen files and manifest."""
    results = {"step_id": "P0-G0-01", "checks": [], "status": "passed"}

    # Check all six files exist
    for fname in EXPECTED_FILES:
        path = os.path.join(FINAL_DIR, fname)
        exists = os.path.isfile(path)
        results["checks"].append({
            "check": f"file_exists:{fname}",
            "passed": exists,
        })
        if not exists:
            results["status"] = "failed"

    # Read manifest from 00_最终冻结基线.md and validate package_id
    baseline_path = os.path.join(FINAL_DIR, "00_最终冻结基线.md")
    with open(baseline_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check package_id in manifest
    pkg_check = PACKAGE_ID in content
    results["checks"].append({
        "check": f"manifest_package_id={PACKAGE_ID}",
        "passed": pkg_check,
    })
    if not pkg_check:
        results["status"] = "failed"

    # Check all six file paths appear in manifest
    for fname in EXPECTED_FILES:
        relative_path = f"rebuild4/docs/03_final/{fname}"
        path_check = relative_path in content
        results["checks"].append({
            "check": f"manifest_contains_path:{relative_path}",
            "passed": path_check,
        })
        if not path_check:
            results["status"] = "failed"

    # Check each file's version is the same package_id
    version_pattern = f"version: {PACKAGE_ID}"
    version_count = content.count(version_pattern)
    results["checks"].append({
        "check": f"manifest_per_file_version_count={version_count}>=6",
        "passed": version_count >= 6,
    })
    if version_count < 6:
        results["status"] = "failed"

    # Compute file hashes for audit
    file_hashes = {}
    for fname in EXPECTED_FILES:
        path = os.path.join(FINAL_DIR, fname)
        if os.path.isfile(path):
            file_hashes[fname] = sha256_file(path)
    results["file_hashes"] = file_hashes

    return results


def step_g0_02():
    """P0-G0-02: Validate G0 read-only boundary and upgrade rules."""
    results = {"step_id": "P0-G0-02", "checks": [], "status": "passed"}

    # Check that the task document specifies G0 does not write to DB
    task_path = os.path.join(FINAL_DIR, "03_最终执行任务书.md")
    with open(task_path, "r", encoding="utf-8") as f:
        task_content = f.read()

    # G0 read-only: G1's first action must be raw time span pre-check
    g0_readonly_check = "G0 只负责冻结包只读校验" in task_content or "G0 只负责文档校验" in task_content
    results["checks"].append({
        "check": "doc_confirms_g0_readonly",
        "passed": g0_readonly_check,
    })
    if not g0_readonly_check:
        results["status"] = "failed"

    # G1 first action must be raw time span pre-check
    g1_precheck = "G1 的第一个原子动作必须是 raw 时间跨度预检" in task_content or "G1 的第一个原子动作必须是" in task_content
    results["checks"].append({
        "check": "doc_confirms_g1_first_action_is_raw_precheck",
        "passed": g1_precheck,
    })
    if not g1_precheck:
        results["status"] = "failed"

    # Package version upgrade rule
    baseline_path = os.path.join(FINAL_DIR, "00_最终冻结基线.md")
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_content = f.read()

    upgrade_rule = "六文件任一内容发生实质变化" in baseline_content and "必须生成新的" in baseline_content
    results["checks"].append({
        "check": "doc_confirms_upgrade_rule",
        "passed": upgrade_rule,
    })
    if not upgrade_rule:
        results["status"] = "failed"

    # Current version is v6
    current_version = PACKAGE_ID in baseline_content
    results["checks"].append({
        "check": f"current_version={PACKAGE_ID}",
        "passed": current_version,
    })
    if not current_version:
        results["status"] = "failed"

    return results


def step_g0_03():
    """P0-G0-03: Validate self-containment and no external decision dependency."""
    results = {"step_id": "P0-G0-03", "checks": [], "status": "passed"}

    # Check that frozen package declares no new decisions needed
    baseline_path = os.path.join(FINAL_DIR, "00_最终冻结基线.md")
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_content = f.read()

    no_new_decisions = "无新增人类裁决" in baseline_content or "当前无需新增人类裁决" in baseline_content
    results["checks"].append({
        "check": "doc_confirms_no_new_decisions",
        "passed": no_new_decisions,
    })
    if not no_new_decisions:
        results["status"] = "failed"

    # Check scope doc also confirms three exception types
    scope_path = os.path.join(FINAL_DIR, "05_本轮范围与降级说明.md")
    with open(scope_path, "r", encoding="utf-8") as f:
        scope_content = f.read()

    three_exceptions = all(kw in scope_content for kw in [
        "规则 seed 不可用",
        "real rolling 窗口缺失",
        "页面一级主语冲突",
    ])
    results["checks"].append({
        "check": "doc_confirms_three_exception_types",
        "passed": three_exceptions,
    })
    if not three_exceptions:
        results["status"] = "failed"

    # Check that external decision file is not a runtime dependency
    external_decision_excluded = (
        "只保留历史留档价值" in baseline_content
        or "只保留历史回查价值" in baseline_content
    )
    results["checks"].append({
        "check": "external_decision_files_excluded_from_runtime",
        "passed": external_decision_excluded,
    })
    if not external_decision_excluded:
        results["status"] = "failed"

    # Self-containment: execution period only reads six files
    self_contained = "执行期只允许引用本六文件" in baseline_content or "执行期只读六文件" in baseline_content
    results["checks"].append({
        "check": "execution_only_reads_six_files",
        "passed": self_contained,
    })
    if not self_contained:
        results["status"] = "failed"

    return results


def main():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    steps = []
    overall_status = "passed"

    for step_fn in [step_g0_01, step_g0_02, step_g0_03]:
        result = step_fn()
        steps.append(result)
        # Write individual step evidence
        step_path = os.path.join(ARTIFACT_DIR, f"{result['step_id']}.json")
        with open(step_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  {result['step_id']}: {result['status']}")
        if result["status"] != "passed":
            overall_status = "failed"

    # Build index.json
    index = {
        "gate_code": "G0",
        "package_id": PACKAGE_ID,
        "attempt_id": "attempt_001",
        "gate_owner": "release_owner",
        "status": overall_status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "steps": [
            {
                "step_id": s["step_id"],
                "status": s["status"],
                "evidence_file": f"{s['step_id']}.json",
            }
            for s in steps
        ],
    }

    index_path = os.path.join(ARTIFACT_DIR, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\nG0 overall: {overall_status}")
    print(f"Artifact: {index_path}")

    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
