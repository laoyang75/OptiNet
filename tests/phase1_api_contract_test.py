#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from fastapi.testclient import TestClient


def assert_error_shape(resp_json: dict) -> bool:
    if not isinstance(resp_json, dict):
        return False
    err = resp_json.get("error")
    if not isinstance(err, dict):
        return False
    return all(k in err for k in ("code", "message", "details"))


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    with tempfile.NamedTemporaryFile(prefix="phase1_contract_issues_", suffix=".json", delete=False) as tmp:
        issue_store_file = tmp.name
    with tempfile.NamedTemporaryFile(prefix="phase1_contract_patches_", suffix=".json", delete=False) as tmp_patch:
        patch_store_file = tmp_patch.name
    os.environ["PHASE1_ISSUE_STORE_FILE"] = issue_store_file
    os.environ["PHASE1_PATCH_STORE_FILE"] = patch_store_file
    def _cleanup_tmp() -> None:
        try:
            Path(issue_store_file).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            Path(patch_store_file).unlink(missing_ok=True)
        except Exception:
            pass

    from apps.phase1_api import server as phase1_api_server  # noqa: E402

    client = TestClient(phase1_api_server.app)
    checks = []

    bad_layer = client.get("/api/phase1/layer/NOT_EXISTS")
    checks.append({"name": "error_shape_not_found", "ok": bad_layer.status_code == 404 and assert_error_shape(bad_layer.json())})

    bad_body = client.post("/api/phase1/issues", json={"title": "missing required fields"})
    checks.append({"name": "error_shape_bad_request", "ok": bad_body.status_code == 400 and assert_error_shape(bad_body.json())})

    rec = client.get("/api/phase1/reconciliation?page=1&page_size=2")
    rec_json = rec.json()
    checks.append(
        {
            "name": "reconciliation_pagination",
            "ok": rec.status_code == 200
            and all(k in rec_json for k in ("page", "page_size", "total", "total_pages"))
            and len(rec_json.get("checks", [])) <= 2,
        }
    )

    exposure = client.get("/api/phase1/exposure-matrix?page=1&page_size=2")
    exposure_json = exposure.json()
    checks.append(
        {
            "name": "exposure_pagination",
            "ok": exposure.status_code == 200
            and all(k in exposure_json for k in ("page", "page_size", "total", "total_pages"))
            and len(exposure_json.get("rows", [])) <= 2,
        }
    )

    issue = client.post(
        "/api/phase1/issues",
        json={
            "run_id": "phase1_contract",
            "severity": "P2",
            "layer_id": "L4_Final",
            "title": "contract issue",
            "status": "new",
        },
    )
    issue_json = issue.json()
    issue_id = int(issue_json.get("item", {}).get("issue_id", 0))
    checks.append({"name": "issue_create_contract", "ok": issue.status_code == 200 and issue_id > 0})

    issue_patch = client.patch(f"/api/phase1/issues/{issue_id}", json={"status": "in_progress"})
    checks.append(
        {
            "name": "issue_patch_contract",
            "ok": issue_patch.status_code == 200 and issue_patch.json().get("item", {}).get("status") == "in_progress",
        }
    )

    issue_patch_invalid = client.patch(f"/api/phase1/issues/{issue_id}", json={"status": "new"})
    checks.append(
        {
            "name": "issue_patch_transition_guard",
            "ok": issue_patch_invalid.status_code == 409 and assert_error_shape(issue_patch_invalid.json()),
        }
    )

    patch_create = client.post(
        "/api/phase1/patches",
        json={
            "issue_id": issue_id,
            "run_id": "phase1_contract",
            "change_type": "sql_fix",
            "change_summary": "sync Step43 with Step40 schema",
            "owner": "contract_tester",
            "verified_flag": False,
        },
    )
    patch_json = patch_create.json()
    patch_id = int(patch_json.get("item", {}).get("patch_id", 0))
    checks.append({"name": "patch_create_contract", "ok": patch_create.status_code == 200 and patch_id > 0})

    patch_list = client.get(f"/api/phase1/patches?issue_id={issue_id}&page=1&page_size=1")
    patch_list_json = patch_list.json()
    checks.append(
        {
            "name": "patch_list_contract",
            "ok": patch_list.status_code == 200
            and all(k in patch_list_json for k in ("page", "page_size", "total", "total_pages"))
            and len(patch_list_json.get("items", [])) <= 1,
        }
    )

    failed = [c for c in checks if not c["ok"]]
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    _cleanup_tmp()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
