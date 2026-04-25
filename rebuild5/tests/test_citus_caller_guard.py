import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "rebuild5" / "backend"
CALLER_FILES = [
    REPO_ROOT / "rebuild5" / "backend" / "app" / "maintenance" / "publish_bs_lac.py",
    REPO_ROOT / "rebuild5" / "backend" / "app" / "maintenance" / "publish_cell.py",
    REPO_ROOT / "rebuild5" / "backend" / "app" / "profile" / "pipeline.py",
    REPO_ROOT / "rebuild5" / "backend" / "app" / "enrichment" / "pipeline.py",
    REPO_ROOT / "rebuild5" / "backend" / "app" / "core" / "database.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_legacy_execute_with_session_settings() -> None:
    hits = [
        str(path.relative_to(REPO_ROOT))
        for path in BACKEND_ROOT.rglob("*.py")
        if "_execute_with_session_settings" in _read(path)
    ]

    assert hits == []


def test_high_risk_callers_use_unified_entry() -> None:
    missing = []
    local_client_cursors = []
    for path in CALLER_FILES:
        text = _read(path)
        if "execute_distributed_insert" not in text:
            missing.append(str(path.relative_to(REPO_ROOT)))
        if "with ClientCursor(" in text:
            local_client_cursors.append(str(path.relative_to(REPO_ROOT)))

    assert missing == []
    assert local_client_cursors == []


def test_no_top_level_circular_import_for_citus_compat() -> None:
    path = REPO_ROOT / "rebuild5" / "backend" / "app" / "core" / "database.py"
    first_50_lines = "\n".join(_read(path).splitlines()[:50])

    assert "from .citus_compat" not in first_50_lines


def test_publish_helpers_no_raw_params_execute() -> None:
    offenders = []
    for path in CALLER_FILES[:2]:
        tree = ast.parse(_read(path), filename=str(path))
        for function in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
            if not function.name.startswith("publish_"):
                continue
            for call in [node for node in ast.walk(function) if isinstance(node, ast.Call)]:
                if not isinstance(call.func, ast.Name) or call.func.id != "execute":
                    continue
                if any(keyword.arg == "params" for keyword in call.keywords):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{function.name}:{call.lineno}")

    assert offenders == []
