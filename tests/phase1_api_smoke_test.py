#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from fastapi.testclient import TestClient


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    with tempfile.NamedTemporaryFile(prefix="phase1_smoke_issues_", suffix=".json", delete=False) as tmp:
        issue_store_file = tmp.name
    with tempfile.NamedTemporaryFile(prefix="phase1_smoke_patches_", suffix=".json", delete=False) as tmp_patch:
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

    checks = [
        ("GET", "/health"),
        ("GET", "/api/phase1/overview"),
        ("GET", "/api/phase1/layer/L4_Final?page=1&page_size=5"),
        ("GET", "/api/phase1/reconciliation?page=1&page_size=5"),
        ("GET", "/api/phase1/exposure-matrix?page=1&page_size=5"),
        ("GET", "/api/phase1/issues?page=1&page_size=5"),
        ("GET", "/api/phase1/patches?page=1&page_size=5"),
        ("GET", "/api/phase1/trace/demo_trace"),
        ("GET", "/api/phase1/dashboard-snapshot"),
    ]

    result = []
    for method, path in checks:
        resp = client.request(method, path)
        ok = resp.status_code == 200
        result.append({"path": path, "status_code": resp.status_code, "ok": ok})
        if not ok:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print(resp.text)
            _cleanup_tmp()
            return 1

    create_resp = client.post(
        "/api/phase1/issues",
        json={
            "run_id": "phase1_smoke",
            "severity": "P2",
            "layer_id": "L4_Final",
            "title": "smoke issue",
            "status": "new",
            "owner": "smoke_tester",
        },
    )
    if create_resp.status_code != 200:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(create_resp.text)
        _cleanup_tmp()
        return 1
    create_data = create_resp.json()
    issue_id = int(create_data.get("item", {}).get("issue_id", 0))
    result.append({"path": "/api/phase1/issues [POST]", "status_code": create_resp.status_code, "ok": issue_id > 0})
    if issue_id <= 0:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(create_resp.text)
        _cleanup_tmp()
        return 1

    patch_resp = client.patch(
        f"/api/phase1/issues/{issue_id}",
        json={"status": "in_progress", "owner": "smoke_tester"},
    )
    patch_ok = patch_resp.status_code == 200 and patch_resp.json().get("item", {}).get("status") == "in_progress"
    result.append({"path": f"/api/phase1/issues/{issue_id} [PATCH]", "status_code": patch_resp.status_code, "ok": patch_ok})
    if not patch_ok:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(patch_resp.text)
        _cleanup_tmp()
        return 1

    patch_resp2 = client.patch(
        f"/api/phase1/issues/{issue_id}",
        json={"status": "verified", "owner": "smoke_tester"},
    )
    patch_ok2 = patch_resp2.status_code == 200 and patch_resp2.json().get("item", {}).get("status") == "verified"
    result.append({"path": f"/api/phase1/issues/{issue_id} [PATCH#2]", "status_code": patch_resp2.status_code, "ok": patch_ok2})
    if not patch_ok2:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(patch_resp2.text)
        _cleanup_tmp()
        return 1

    patch_create_resp = client.post(
        "/api/phase1/patches",
        json={
            "issue_id": issue_id,
            "run_id": "phase1_smoke",
            "change_type": "sql_fix",
            "change_summary": "adjust Step43 aggregation columns",
            "owner": "smoke_tester",
            "verified_flag": True,
        },
    )
    patch_create_ok = patch_create_resp.status_code == 200 and int(
        patch_create_resp.json().get("item", {}).get("patch_id", 0)
    ) > 0
    result.append({"path": "/api/phase1/patches [POST]", "status_code": patch_create_resp.status_code, "ok": patch_create_ok})
    if not patch_create_ok:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(patch_create_resp.text)
        _cleanup_tmp()
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    _cleanup_tmp()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
