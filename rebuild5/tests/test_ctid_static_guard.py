import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "rebuild5" / "backend"
SCRIPTS_ROOT = REPO_ROOT / "rebuild5" / "scripts"
CTID_READ_PROJECTION = "rebuild5/backend/app/etl/fill.py"


def _python_files() -> list[Path]:
    files = []
    for root in (BACKEND_ROOT, SCRIPTS_ROOT):
        files.extend(root.rglob("*.py"))
    return sorted(files)


def _strings_with_locations(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    parts.append(ast.unparse(value.value))
            values.append((node.lineno, "".join(parts)))
    return values


def test_no_distributed_delete_with_ctid_where() -> None:
    offenders = []
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, sql in _strings_with_locations(path):
            lowered = sql.lower()
            if "ctid" not in lowered:
                continue
            if rel == CTID_READ_PROJECTION and "ctid::text" in lowered and "delete from" not in lowered:
                continue
            if "delete from" in lowered:
                offenders.append(f"{rel}:{lineno}")

    assert offenders == []


def test_publish_bs_does_not_use_ctid_anywhere() -> None:
    path = BACKEND_ROOT / "app" / "maintenance" / "publish_bs_lac.py"

    assert "ctid" not in path.read_text(encoding="utf-8").lower()
