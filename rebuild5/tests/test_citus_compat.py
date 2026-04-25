from rebuild5.backend.app.core import citus_compat


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class SpyCursor:
    instances = []

    def __init__(self, conn):
        self.conn = conn
        self.executed = []
        self.mogrified = []
        SpyCursor.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def mogrify(self, sql, params):
        self.mogrified.append((sql, params))
        return f"MOGRIFIED::{sql}::{params!r}"

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


def _patch_connection(monkeypatch) -> None:
    SpyCursor.instances.clear()
    monkeypatch.setattr(citus_compat, "get_conn", lambda: FakeConnection())
    monkeypatch.setattr(citus_compat, "ClientCursor", SpyCursor)


def test_uses_client_cursor_for_params(monkeypatch) -> None:
    _patch_connection(monkeypatch)

    citus_compat.execute_distributed_insert("INSERT INTO rb5.t SELECT %s", params=(1,))

    assert len(SpyCursor.instances) == 1
    cursor = SpyCursor.instances[0]
    assert cursor.mogrified == [("INSERT INTO rb5.t SELECT %s", (1,))]
    assert cursor.executed == [("MOGRIFIED::INSERT INTO rb5.t SELECT %s::(1,)", None)]


def test_no_params_skips_mogrify(monkeypatch) -> None:
    _patch_connection(monkeypatch)

    citus_compat.execute_distributed_insert("INSERT INTO rb5.t VALUES (1)")

    cursor = SpyCursor.instances[0]
    assert cursor.mogrified == []
    assert cursor.executed == [("INSERT INTO rb5.t VALUES (1)", None)]


def test_session_setup_executed_and_reset_in_reverse(monkeypatch) -> None:
    _patch_connection(monkeypatch)

    citus_compat.execute_distributed_insert(
        "INSERT INTO rb5.t SELECT 1",
        session_setup_sqls=[
            "SELECT 1",
            "SET enable_nestloop = off",
            "SET work_mem = '1GB'",
        ],
    )

    cursor = SpyCursor.instances[0]
    assert cursor.executed == [
        ("SELECT 1", None),
        ("SET enable_nestloop = off", None),
        ("SET work_mem = '1GB'", None),
        ("INSERT INTO rb5.t SELECT 1", None),
        ("RESET work_mem", None),
        ("RESET enable_nestloop", None),
    ]
