import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "rebuild5" / "backend"
SCRIPTS_ROOT = REPO_ROOT / "rebuild5" / "scripts"
WINDOW_PATH = BACKEND_ROOT / "app" / "maintenance" / "window.py"


def _window_text() -> str:
    return WINDOW_PATH.read_text(encoding="utf-8")


def _sql_strings_in_function(function_name: str) -> list[str]:
    tree = ast.parse(_window_text(), filename=str(WINDOW_PATH))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    strings = []
    for node in ast.walk(function):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    parts.append(ast.unparse(value.value))
            strings.append("".join(parts))
    return strings


def _trim_sql() -> str:
    candidates = [
        sql
        for sql in _sql_strings_in_function("refresh_sliding_window")
        if "DELETE FROM rb5.cell_sliding_window" in sql
    ]
    assert candidates
    return max(candidates, key=len)


def test_trim_uses_pk_delete_not_ctid() -> None:
    sql = _trim_sql()
    lowered = sql.lower()

    assert "delete from rb5.cell_sliding_window" in lowered
    assert "where" in lowered
    assert "ctid" not in lowered
    assert "batch_id, source_row_uid, cell_id" in lowered
    assert "using delete_keys d" in lowered
    assert "w.batch_id = d.batch_id" in lowered
    assert "w.source_row_uid = d.source_row_uid" in lowered
    assert "w.cell_id = d.cell_id" in lowered


def test_trim_retention_window_clause_present() -> None:
    sql = _trim_sql()

    assert "WINDOW_RETENTION_DAYS" in sql or "INTERVAL '14 days'" in sql
    assert "obs_rank" in sql
    assert "WINDOW_MIN_OBS" in sql or "1000" in sql


def test_no_skip_sliding_window_trim_env_var() -> None:
    hits = []
    for root in (BACKEND_ROOT, SCRIPTS_ROOT):
        for path in root.rglob("*.py"):
            if "REBUILD5_SKIP_SLIDING_WINDOW_TRIM" in path.read_text(encoding="utf-8"):
                hits.append(str(path.relative_to(REPO_ROOT)))

    assert hits == []
