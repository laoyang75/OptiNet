import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "rebuild5" / "scripts" / "run_citus_serial_batches.py"
PIPELINED_RUNNER_PATH = REPO_ROOT / "rebuild5" / "scripts" / "run_citus_pipelined_batches.py"
ARTIFACT_PIPELINED_RUNNER_PATH = REPO_ROOT / "rebuild5" / "scripts" / "run_citus_artifact_pipelined.py"


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


def test_pipelined_runner_calls_materialize_step2_scope_after_step1() -> None:
    """Guard same-day order in the pipelined runner.

    Step 1 for day N+1 may overlap with Step 2-5 for day N, but for the same
    day the runner must finish Step 1, materialize the daily Step 2 scope, and
    only then enqueue Step 2-5.
    """
    text = PIPELINED_RUNNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(PIPELINED_RUNNER_PATH))
    producer_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_step1_producer"
    ]

    assert len(producer_defs) == 1
    producer = producer_defs[0]
    positions = {}
    for child in ast.walk(producer):
        name = _call_name(child)
        if name in {"run_step1_pipeline", "materialize_step2_scope", "put"}:
            positions.setdefault(name, child.lineno)

    assert positions["run_step1_pipeline"] < positions["materialize_step2_scope"]
    assert positions["materialize_step2_scope"] < positions["put"]
    assert 'DROP TABLE IF EXISTS rb5._step2_cell_input' in text

    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.endswith("run_daily_increment_batch_loop")
        and any(alias.name == "materialize_step2_scope" for alias in node.names)
    ]
    assert len(imports) == 1


def test_artifact_pipelined_runner_freezes_before_consumer() -> None:
    """Guard artifact-driven runner ordering and explicit Step 2 input."""
    text = ARTIFACT_PIPELINED_RUNNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(ARTIFACT_PIPELINED_RUNNER_PATH))
    producer_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_step1_artifact_producer"
    ]
    consumer_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_artifact_consumer"
    ]

    assert len(producer_defs) == 1
    assert len(consumer_defs) == 1
    positions = {}
    for child in ast.walk(producer_defs[0]):
        name = _call_name(child)
        if name in {"run_step1_pipeline", "freeze_step2_input_artifact", "put"}:
            positions.setdefault(name, child.lineno)

    assert positions["run_step1_pipeline"] < positions["freeze_step2_input_artifact"]
    assert positions["freeze_step2_input_artifact"] < positions["put"]

    consumer = consumer_defs[0]
    consumer_calls = [node for node in ast.walk(consumer) if isinstance(node, ast.Call)]
    profile_calls = [node for node in consumer_calls if _call_name(node) == "run_profile_pipeline"]
    assert len(profile_calls) == 1
    assert any(keyword.arg == "input_relation" for keyword in profile_calls[0].keywords)
    assert "_ready_artifact_relation" in text
    assert "FROM rb5_meta.pipeline_artifacts" in text
