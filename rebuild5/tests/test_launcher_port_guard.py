import subprocess
import sys
from pathlib import Path

import pytest

from rebuild5.launcher import launcher


def test_find_port_owners_parses_lsof_output(monkeypatch) -> None:
    sample = 'COMMAND   PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\nPython  4321   demo   10u  IPv4 0x123      0t0  TCP 127.0.0.1:47230 (LISTEN)\n'

    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=sample, stderr=''),
    )

    owners = launcher.find_port_owners('127.0.0.1', 47230)

    assert owners == [{'pid': 4321, 'command': 'Python', 'raw': 'Python  4321   demo   10u  IPv4 0x123      0t0  TCP 127.0.0.1:47230 (LISTEN)'}]


def test_build_launcher_port_conflict_message_mentions_cleanup(monkeypatch) -> None:
    monkeypatch.setattr(
        launcher,
        'find_port_owners',
        lambda host, port: [{'pid': 4321, 'command': 'Python', 'raw': 'Python 4321 LISTEN'}],
    )

    message = launcher.build_launcher_port_conflict_message('127.0.0.1', 47230)

    assert '47230' in message
    assert '4321' in message
    assert 'launcher' in message.lower()
    assert '清理' in message


def test_terminate_port_owners_kills_every_pid(monkeypatch) -> None:
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        launcher,
        'find_port_owners',
        lambda host, port: [
            {'pid': 111, 'command': 'python', 'raw': 'python 111'},
            {'pid': 222, 'command': 'node', 'raw': 'node 222'},
        ],
    )
    monkeypatch.setattr(launcher.os, 'kill', lambda pid, sig: killed.append((pid, sig)))

    result = launcher.terminate_port_owners('127.0.0.1', 47230)

    assert result['ok'] is True
    assert result['killed_pids'] == [111, 222]
    assert killed == [(111, launcher.signal.SIGTERM), (222, launcher.signal.SIGTERM)]


def test_main_falls_back_to_next_free_port_when_launcher_port_is_occupied(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    host = '127.0.0.1'
    requested_port = 47230
    fallback_port = 47233
    bound: dict[str, tuple[str, int]] = {}

    class FakeServer:
        def __init__(self, address: tuple[str, int], _handler: object) -> None:
            bound['address'] = address

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            return None

    monkeypatch.setattr(sys, 'argv', ['launcher.py', '--host', host, '--port', str(requested_port)])
    monkeypatch.setattr(launcher, 'find_port_owners', lambda _host, _port: [{'pid': 9876, 'command': 'pytest', 'raw': 'pytest 9876'}])
    monkeypatch.setattr(launcher, 'RUNTIME_ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'find_available_port', lambda _host, _port, span=20, reserved_ports=None: fallback_port)
    monkeypatch.setattr(launcher, 'ThreadingHTTPServer', FakeServer)

    launcher.main()

    assert bound['address'] == (host, fallback_port)
    output = capsys.readouterr().err
    assert str(requested_port) in output
    assert str(fallback_port) in output
    assert '9876' in output
