import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "rebuild5" / "scripts" / "run_citus_serial_batches.py"


def _runner_text() -> str:
    return RUNNER_PATH.read_text(encoding="utf-8")


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_serial_runner_calls_materialize_step2_scope_after_step1() -> None:
    text = _runner_text()
    tree = ast.parse(text, filename=str(RUNNER_PATH))
    loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and any(_call_name(child) == "run_step1_pipeline" for child in ast.walk(node))
        and any(_call_name(child) == "materialize_step2_scope" for child in ast.walk(node))
        and any(_call_name(child) == "run_profile_pipeline" for child in ast.walk(node))
    ]

    assert len(loops) == 1
    loop = loops[0]
    positions = {}
    for child in ast.walk(loop):
        name = _call_name(child)
        if name in {"run_step1_pipeline", "materialize_step2_scope", "run_profile_pipeline"}:
            positions[name] = child.lineno

    assert positions["run_step1_pipeline"] < positions["materialize_step2_scope"]
    assert positions["materialize_step2_scope"] < positions["run_profile_pipeline"]
    assert 'DROP TABLE IF EXISTS rb5._step2_cell_input' in text


def test_materialize_step2_scope_imported_from_daily_loop() -> None:
    tree = ast.parse(_runner_text(), filename=str(RUNNER_PATH))
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.endswith("run_daily_increment_batch_loop")
        and any(alias.name == "materialize_step2_scope" for alias in node.names)
    ]

    assert len(imports) == 1
