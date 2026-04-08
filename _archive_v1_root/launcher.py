#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parent
RUN_LOG_DIR = ROOT_DIR / "docs" / "phase1" / "dev" / "run_logs"
PID_FILE = RUN_LOG_DIR / "phase1_api.pid"
LOG_FILE = RUN_LOG_DIR / "phase1_api_server.log"

DEFAULT_ENV = {
    "PHASE1_DB_DSN": "postgresql://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable",
    "PHASE1_API_HOST": "127.0.0.1",
    "PHASE1_API_PORT": "8508",
    "PHASE1_PAGE_SIZE": "100",
    "PHASE1_MAX_PAGE_SIZE": "500",
}

UI_PAGE_MAP: Dict[str, str] = {
    "dashboard": "apps/phase1_ui/dashboard.html",
    "layer": "apps/phase1_ui/layer.html",
    "reconciliation": "apps/phase1_ui/reconciliation.html",
    "exposure": "apps/phase1_ui/exposure.html",
    "issues": "apps/phase1_ui/issues.html",
    "patches": "apps/phase1_ui/patches.html",
    "glossary": "apps/phase1_ui/glossary.html",
}

ACTION_LOCK = threading.Lock()


def _mask_dsn(dsn: str) -> str:
    text = str(dsn or "")
    if "@" not in text or "://" not in text:
        return text
    prefix, suffix = text.split("://", 1)
    auth_host = suffix
    if "@" not in auth_host:
        return text
    auth, host_part = auth_host.split("@", 1)
    if ":" in auth:
        user = auth.split(":", 1)[0]
        return f"{prefix}://{user}:***@{host_part}"
    return text


def _runtime_env() -> Dict[str, str]:
    env = os.environ.copy()
    for k, v in DEFAULT_ENV.items():
        env.setdefault(k, v)
    return env


def _ensure_run_dir() -> None:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _read_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    text = PID_FILE.read_text(encoding="utf-8").strip()
    if not text.isdigit():
        return None
    return int(text)


def _write_pid(pid: int) -> None:
    _ensure_run_dir()
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health_url(env: Dict[str, str]) -> str:
    host = env["PHASE1_API_HOST"]
    port = env["PHASE1_API_PORT"]
    return f"http://{host}:{port}/health"


def _api_docs_url(env: Dict[str, str]) -> str:
    host = env["PHASE1_API_HOST"]
    port = env["PHASE1_API_PORT"]
    return f"http://{host}:{port}/docs"


def _fetch_health_data(env: Dict[str, str]) -> Tuple[bool, Optional[Dict[str, object]], str]:
    url = _health_url(env)
    try:
        with urllib.request.urlopen(url, timeout=1.2) as r:
            text = r.read().decode("utf-8", errors="replace")
        data = json.loads(text)
        if isinstance(data, dict):
            return True, data, ""
        return True, {"raw": text}, ""
    except Exception as exc:
        return False, None, str(exc)


def _status_data() -> Dict[str, object]:
    env = _runtime_env()
    pid = _read_pid()
    running = bool(pid and _is_process_alive(pid))
    health_ok, health_json, health_error = _fetch_health_data(env)
    return {
        "running": running,
        "pid": pid if pid else None,
        "log": str(LOG_FILE),
        "db_dsn": _mask_dsn(env.get("PHASE1_DB_DSN", "")),
        "health_url": _health_url(env),
        "api_docs_url": _api_docs_url(env),
        "health_ok": health_ok,
        "health_json": health_json,
        "health_error": health_error,
        "pages": sorted(list(UI_PAGE_MAP.keys()) + ["api-docs", "health"]),
    }


def _start() -> int:
    env = _runtime_env()
    existing = _read_pid()
    if existing and _is_process_alive(existing):
        print(f"Phase1 API already running (pid={existing}).")
        print(f"Health: {_health_url(env)}")
        return 0

    _ensure_run_dir()
    with LOG_FILE.open("ab") as logf:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.phase1_api.server:app",
            "--app-dir",
            str(ROOT_DIR),
            "--host",
            env["PHASE1_API_HOST"],
            "--port",
            env["PHASE1_API_PORT"],
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
        )
    _write_pid(proc.pid)
    time.sleep(0.8)
    if proc.poll() is not None:
        _clear_pid()
        print("Failed to start Phase1 API. See log:")
        print(str(LOG_FILE))
        return 1

    print(f"Phase1 API started (pid={proc.pid}).")
    print(f"Health: {_health_url(env)}")
    print(f"Log: {LOG_FILE}")
    return 0


def _stop() -> int:
    pid = _read_pid()
    if not pid:
        print("Phase1 API is not running (pid file not found).")
        return 0
    if not _is_process_alive(pid):
        _clear_pid()
        print("Phase1 API is not running (stale pid file removed).")
        return 0

    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as exc:
            print(f"Failed to stop pid={pid}: {exc}")
            return 1

    deadline = time.time() + 8.0
    while time.time() < deadline:
        if not _is_process_alive(pid):
            _clear_pid()
            print(f"Phase1 API stopped (pid={pid}).")
            return 0
        time.sleep(0.2)

    try:
        os.killpg(pid, signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    _clear_pid()
    print(f"Phase1 API force-stopped (pid={pid}).")
    return 0


def _status() -> int:
    s = _status_data()
    print(f"running: {s['running']}")
    print(f"pid: {s['pid'] if s['pid'] else '-'}")
    print(f"log: {s['log']}")
    print(f"db_dsn: {s['db_dsn']}")
    print(f"health_url: {s['health_url']}")
    if s["health_ok"]:
        print(f"health: ok {json.dumps(s['health_json'], ensure_ascii=False)}")
    else:
        print(f"health: unavailable ({s['health_error']})")
    return 0


def _open(target: str) -> int:
    env = _runtime_env()
    if target == "all":
        opened = []
        for name in ("dashboard", "issues", "patches", "glossary"):
            page = UI_PAGE_MAP[name]
            url = (ROOT_DIR / page).resolve().as_uri()
            webbrowser.open(url)
            opened.append(url)
        print("Opened:")
        for u in opened:
            print(u)
        return 0

    if target == "api-docs":
        url = _api_docs_url(env)
    elif target == "health":
        url = _health_url(env)
    else:
        page = UI_PAGE_MAP.get(target)
        if not page:
            valid = ", ".join(list(UI_PAGE_MAP.keys()) + ["api-docs", "health", "all"])
            print(f"Unknown page '{target}'. valid: {valid}")
            return 1
        url = (ROOT_DIR / page).resolve().as_uri()
    webbrowser.open(url)
    print(f"Opened: {url}")
    return 0


def _print_env() -> int:
    env = _runtime_env()
    for k in ("PHASE1_DB_DSN", "PHASE1_API_HOST", "PHASE1_API_PORT", "PHASE1_PAGE_SIZE", "PHASE1_MAX_PAGE_SIZE"):
        print(f"{k}={env.get(k, '')}")
    return 0


def _console_html() -> str:
    options = "\n".join([f'<option value="{k}">{k}</option>' for k in sorted(UI_PAGE_MAP.keys())])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Phase1 控制台</title>
  <style>
    :root {{
      --bg: #f3f7ef;
      --ink: #143038;
      --muted: #4f6870;
      --line: #d8e3df;
      --card: #ffffff;
      --ok: #1f9d66;
      --bad: #c73939;
      --accent: #1a7f93;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Noto Sans SC", "PingFang SC", sans-serif;
      color: var(--ink);
      background: linear-gradient(140deg, #f4f8ef, #e3f1ef);
    }}
    .wrap {{ max-width: 1040px; margin: 0 auto; padding: 22px 16px 34px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    .sub {{ color: var(--muted); margin: 0; font-size: 13px; }}
    .row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .btn {{
      border: 0;
      border-radius: 10px;
      background: var(--accent);
      color: #fff;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
    }}
    .btn.gray {{ background: #5f7179; }}
    .btn.red {{ background: #b53d3d; }}
    .pill {{
      display: inline-block;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 4px 10px;
      font-size: 12px;
      color: var(--muted);
      background: #f2f7f6;
    }}
    .ok {{ color: var(--ok); font-weight: 700; }}
    .bad {{ color: var(--bad); font-weight: 700; }}
    pre {{
      margin: 8px 0 0;
      background: #f7fbfa;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      font-size: 12px;
      line-height: 1.45;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    select {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 13px;
      color: var(--ink);
      background: #fcfefd;
    }}
    a {{ color: #1a6a82; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card">
      <h1>Phase1 本地控制台</h1>
      <p class="sub">可点击启动/停止服务、查看状态、打开页面。状态每 2 秒自动刷新。</p>
    </section>

    <section class="card">
      <div class="row">
        <button class="btn" onclick="act('start')">启动服务</button>
        <button class="btn gray" onclick="act('restart')">重启服务</button>
        <button class="btn red" onclick="act('stop')">关闭服务</button>
        <button class="btn gray" onclick="loadStatus()">刷新状态</button>
        <span id="running-pill" class="pill">状态加载中...</span>
      </div>
      <div style="margin-top:8px" class="row">
        <a id="health-link" target="_blank" href="#">health</a>
        <a id="docs-link" target="_blank" href="#">api docs</a>
      </div>
    </section>

    <section class="card">
      <div class="row">
        <select id="page-select">
          {options}
          <option value="api-docs">api-docs</option>
          <option value="health">health</option>
          <option value="all">all(常用页)</option>
        </select>
        <button class="btn" onclick="openPage()">打开页面</button>
      </div>
      <p class="sub" style="margin-top:8px;">all 会依次打开 dashboard / issues / patches / glossary。</p>
    </section>

    <section class="card">
      <div class="pill">服务详情</div>
      <pre id="status-block"></pre>
    </section>

    <section class="card">
      <div class="pill">最近操作</div>
      <pre id="op-block">等待操作...</pre>
    </section>
  </div>
<script>
  async function req(path, method='GET', body=null) {{
    const opt = {{ method, headers: {{ 'Content-Type': 'application/json' }} }};
    if (body !== null) opt.body = JSON.stringify(body);
    const res = await fetch(path, opt);
    const data = await res.json().catch(() => ({{}}));
    return {{ ok: res.ok, status: res.status, data }};
  }}

  function renderStatus(s) {{
    const runningPill = document.getElementById('running-pill');
    const healthLink = document.getElementById('health-link');
    const docsLink = document.getElementById('docs-link');
    const statusBlock = document.getElementById('status-block');

    runningPill.innerHTML = s.running
      ? '<span class="ok">服务运行中</span> pid=' + (s.pid || '-')
      : '<span class="bad">服务未运行</span>';

    healthLink.href = s.health_url || '#';
    healthLink.textContent = s.health_url || 'health';
    docsLink.href = s.api_docs_url || '#';
    docsLink.textContent = s.api_docs_url || 'api docs';

    const lines = [
      'running: ' + s.running,
      'pid: ' + (s.pid || '-'),
      'health_ok: ' + s.health_ok,
      'db_dsn: ' + (s.db_dsn || ''),
      'log: ' + (s.log || ''),
      'health_url: ' + (s.health_url || ''),
      'health_json: ' + JSON.stringify(s.health_json || null, null, 2),
      'health_error: ' + (s.health_error || '')
    ];
    statusBlock.textContent = lines.join('\\n');
  }}

  function setOp(msg) {{
    document.getElementById('op-block').textContent = msg;
  }}

  async function loadStatus() {{
    const r = await req('/api/status');
    if (!r.ok) {{
      setOp('状态查询失败: HTTP ' + r.status);
      return;
    }}
    renderStatus(r.data.status);
  }}

  async function act(action) {{
    setOp('执行中: ' + action + ' ...');
    const r = await req('/api/' + action, 'POST', {{}});
    if (!r.ok || !r.data.ok) {{
      setOp('操作失败: ' + action + '\\n' + JSON.stringify(r.data, null, 2));
      await loadStatus();
      return;
    }}
    setOp('操作成功: ' + action);
    renderStatus(r.data.status);
  }}

  async function openPage() {{
    const page = document.getElementById('page-select').value;
    const r = await req('/api/open', 'POST', {{ page }});
    if (!r.ok || !r.data.ok) {{
      setOp('打开失败: ' + page + '\\n' + JSON.stringify(r.data, null, 2));
      return;
    }}
    setOp('已打开: ' + (r.data.opened || []).join(', '));
  }}

  loadStatus();
  setInterval(loadStatus, 2000);
</script>
</body>
</html>"""


def _json_response(handler: BaseHTTPRequestHandler, status_code: int, payload: Dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, object]:
    raw_len = handler.headers.get("Content-Length", "").strip()
    if not raw_len:
        return {}
    try:
        n = int(raw_len)
    except ValueError:
        return {}
    if n <= 0:
        return {}
    data = handler.rfile.read(n)
    if not data:
        return {}
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "Phase1LauncherConsole/0.1"

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = _console_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if path == "/api/status":
            _json_response(self, 200, {"ok": True, "status": _status_data()})
            return
        _json_response(self, 404, {"ok": False, "message": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        payload = _read_json_body(self)
        if path == "/api/start":
            with ACTION_LOCK:
                code = _start()
            _json_response(self, 200, {"ok": code == 0, "status": _status_data()})
            return
        if path == "/api/stop":
            with ACTION_LOCK:
                code = _stop()
            _json_response(self, 200, {"ok": code == 0, "status": _status_data()})
            return
        if path == "/api/restart":
            with ACTION_LOCK:
                _stop()
                code = _start()
            _json_response(self, 200, {"ok": code == 0, "status": _status_data()})
            return
        if path == "/api/open":
            page = str(payload.get("page", "dashboard"))
            code = _open(page)
            opened = ["dashboard", "issues", "patches", "glossary"] if page == "all" else [page]
            _json_response(self, 200, {"ok": code == 0, "opened": opened, "status": _status_data()})
            return
        _json_response(self, 404, {"ok": False, "message": "not found"})


def _run_console(host: str, port: int, auto_open: bool) -> int:
    server = ThreadingHTTPServer((host, port), ConsoleHandler)
    url = f"http://{host}:{port}/"
    print(f"Phase1 launcher console running: {url}")
    if auto_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase1 Launcher: start/stop service and open pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 launcher.py\n"
            "  python3 launcher.py console\n"
            "  python3 launcher.py start\n"
            "  python3 launcher.py stop\n"
            "  python3 launcher.py status\n"
            "  python3 launcher.py open dashboard\n"
            "  python3 launcher.py restart --open dashboard\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="start Phase1 API service")
    p_start.add_argument("--open", dest="open_page", default="", help="open page after start")

    sub.add_parser("stop", help="stop Phase1 API service")
    p_restart = sub.add_parser("restart", help="restart Phase1 API service")
    p_restart.add_argument("--open", dest="open_page", default="", help="open page after restart")
    sub.add_parser("status", help="show Phase1 API status")

    p_open = sub.add_parser("open", help="open a page in browser")
    p_open.add_argument("page", nargs="?", default="dashboard", help="dashboard/layer/reconciliation/exposure/issues/patches/glossary/api-docs/health/all")

    p_console = sub.add_parser("console", help="open clickable local web console")
    p_console.add_argument("--host", default="127.0.0.1", help="console host, default 127.0.0.1")
    p_console.add_argument("--port", type=int, default=8510, help="console port, default 8510")
    p_console.add_argument("--no-open", action="store_true", help="do not auto-open browser")

    sub.add_parser("env", help="print launcher env")

    args = parser.parse_args()
    if args.cmd is None:
        return _run_console("127.0.0.1", 8510, True)
    cmd = args.cmd

    if cmd == "start":
        code = _start()
        if code == 0 and args.open_page:
            _open(args.open_page)
        return code
    if cmd == "stop":
        return _stop()
    if cmd == "restart":
        _stop()
        code = _start()
        if code == 0 and args.open_page:
            _open(args.open_page)
        return code
    if cmd == "status":
        return _status()
    if cmd == "open":
        return _open(args.page)
    if cmd == "console":
        return _run_console(args.host, args.port, not args.no_open)
    if cmd == "env":
        return _print_env()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
