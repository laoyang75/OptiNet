#!/usr/bin/env python3
"""
望优数仓工作台 rebuild2 — Web Launcher
管理面板：端口 9100，后端服务：端口 8100。
"""

import json
import os
import signal
import subprocess
import sys
import time
import threading
import webbrowser
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.request import urlopen

# ── Config ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
PID_FILE = BACKEND_DIR / ".uvicorn.pid"
LOG_FILE = BACKEND_DIR / "logs" / "uvicorn.log"
LAUNCHER_PORT = 9100
BACKEND_PORT = 8100
BACKEND_HOST = "0.0.0.0"


# ── Service Management ───────────────────────────────────────────────

def get_pid():
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, 0)
            return pid
        except OSError:
            PID_FILE.unlink(missing_ok=True)
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{BACKEND_PORT}"], stderr=subprocess.DEVNULL, text=True
        )
        pids = out.strip().split("\n")
        if pids and pids[0]:
            return int(pids[0])
    except Exception:
        pass
    return None


def is_running():
    return get_pid() is not None


def health_check():
    try:
        r = urlopen(f"http://127.0.0.1:{BACKEND_PORT}/api/v1/health", timeout=3)
        return json.loads(r.read())
    except Exception:
        return None


def get_uptime(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "etime=", "-p", str(pid)], text=True)
        return out.strip()
    except Exception:
        return None


def start_service():
    if is_running():
        return {"ok": False, "msg": f"已在运行 (PID: {get_pid()})"}
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
         "--host", BACKEND_HOST, "--port", str(BACKEND_PORT),
         "--workers", "1", "--log-level", "info"],
        cwd=str(BACKEND_DIR),
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    for _ in range(15):
        time.sleep(1)
        if health_check():
            return {"ok": True, "msg": f"已启动 (PID: {proc.pid})", "pid": proc.pid}
    return {"ok": False, "msg": "已启动但健康检查 15 秒后仍失败"}


def stop_service():
    pid = get_pid()
    if pid is None:
        return {"ok": True, "msg": "未在运行"}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    for _ in range(10):
        time.sleep(1)
        try:
            os.kill(pid, 0)
        except OSError:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    PID_FILE.unlink(missing_ok=True)
    return {"ok": True, "msg": f"已停止 (PID: {pid})"}


def restart_service():
    stop_service()
    time.sleep(1)
    return start_service()


def kill_port():
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{BACKEND_PORT}"], stderr=subprocess.DEVNULL, text=True
        )
        pids = [int(p) for p in out.strip().split("\n") if p.strip()]
    except Exception:
        pids = []
    if not pids:
        return {"ok": True, "msg": f"端口 {BACKEND_PORT} 空闲"}
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    PID_FILE.unlink(missing_ok=True)
    time.sleep(1)
    return {"ok": True, "msg": f"已杀死 {len(pids)} 个进程"}


def get_status():
    pid = get_pid()
    running = pid is not None
    health = health_check() if running else None
    uptime = get_uptime(pid) if running else None
    log_lines = []
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text(errors="replace").strip().split("\n")
        log_lines = lines[-80:]
    log_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    return {
        "running": running,
        "pid": pid,
        "port": BACKEND_PORT,
        "uptime": uptime,
        "health": health,
        "log_lines": log_lines,
        "log_size": log_size,
    }


# ── HTTP Handler ─────────────────────────────────────────────────────

class LauncherHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._html(HTML_PAGE)
        elif self.path == "/api/status":
            self._json(get_status())
        else:
            self.send_error(404)

    def do_POST(self):
        actions = {
            "/api/start": start_service,
            "/api/stop": stop_service,
            "/api/restart": restart_service,
            "/api/killport": kill_port,
        }
        fn = actions.get(self.path)
        if fn:
            self._json(fn())
        else:
            self.send_error(404)


# ── HTML Page ────────────────────────────────────────────────────────

HTML_PAGE = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>望优数仓工作台 — 启动器</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
:root {{
  --bg: #f0f2f5; --card: #ffffff; --border: #e5e7eb;
  --text: #1f2937; --dim: #6b7280; --blue: #3b82f6;
  --green: #10b981; --red: #ef4444; --orange: #f59e0b; --purple: #8b5cf6;
}}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
a {{ color: var(--blue); }}
.container {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
.header {{ text-align: center; margin-bottom: 32px; }}
.header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
.header p {{ color: var(--dim); font-size: 13px; }}
.status-card {{
  background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 24px; margin-bottom: 20px;
  display: flex; align-items: center; gap: 20px;
}}
.status-dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }}
.status-dot.on {{ background: var(--green); box-shadow: 0 0 10px rgba(16,185,129,0.4); }}
.status-dot.off {{ background: var(--red); box-shadow: 0 0 10px rgba(239,68,68,0.25); }}
.status-info {{ flex: 1; }}
.status-label {{ font-size: 18px; font-weight: 700; }}
.status-meta {{ color: var(--dim); font-size: 12px; margin-top: 2px; }}
.status-health {{ font-size: 12px; padding: 3px 10px; border-radius: 20px; }}
.status-health.ok {{ background: #ecfdf5; color: #059669; }}
.status-health.err {{ background: #fef2f2; color: #dc2626; }}
.actions {{
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  margin-bottom: 20px;
}}
.btn {{
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 16px 8px; border-radius: 10px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); cursor: pointer;
  font-size: 13px; font-weight: 500; transition: all 0.2s;
}}
.btn:hover {{ border-color: var(--blue); background: #f0f7ff; }}
.btn:active {{ transform: scale(0.97); }}
.btn.loading {{ opacity: 0.5; pointer-events: none; }}
.btn .icon {{ font-size: 24px; }}
.btn-start .icon {{ color: var(--green); }}
.btn-stop .icon {{ color: var(--red); }}
.btn-restart .icon {{ color: var(--orange); }}
.btn-kill .icon {{ color: var(--purple); }}
.pages-title {{ font-size: 13px; color: var(--dim); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }}
.pages {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;
  margin-bottom: 20px;
}}
.page-link {{
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-radius: 10px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); text-decoration: none;
  font-size: 13px; transition: all 0.2s;
}}
.page-link:hover {{ border-color: var(--blue); background: #f0f7ff; }}
.page-link .dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.page-link .label {{ flex: 1; }}
.page-link .arrow {{ color: var(--dim); }}
.toast {{
  position: fixed; top: 20px; right: 20px; padding: 12px 20px;
  border-radius: 8px; font-size: 13px; font-weight: 500;
  transform: translateY(-20px); opacity: 0; transition: all 0.3s; z-index: 999;
}}
.toast.show {{ transform: translateY(0); opacity: 1; }}
.toast.ok {{ background: #059669; color: #fff; box-shadow: 0 4px 12px rgba(5,150,105,0.3); }}
.toast.err {{ background: #dc2626; color: #fff; box-shadow: 0 4px 12px rgba(220,38,38,0.3); }}
.log-panel {{
  background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
}}
.log-header {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px; border-bottom: 1px solid var(--border);
}}
.log-header span {{ font-size: 13px; font-weight: 600; }}
.log-header small {{ color: var(--dim); font-size: 11px; }}
.log-body {{
  padding: 12px 16px; max-height: 360px; overflow-y: auto;
  font-family: 'SF Mono', 'Menlo', monospace; font-size: 11px; line-height: 1.6;
  color: #4b5563; white-space: pre-wrap; word-break: break-all; background: #f9fafb;
}}
.log-body .err {{ color: var(--red); }}
.log-body .warn {{ color: var(--orange); }}
.log-body .info {{ color: var(--blue); }}
@media (max-width: 640px) {{
  .actions {{ grid-template-columns: repeat(2, 1fr); }}
  .pages {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>望优数仓工作台 rebuild2</h1>
    <p>数据驱动的分层重构 &mdash; 启动器 (:{LAUNCHER_PORT}) &rarr; 后端 (:{BACKEND_PORT})</p>
  </div>

  <div class="status-card" id="status-card">
    <div class="status-dot off" id="status-dot"></div>
    <div class="status-info">
      <div class="status-label" id="status-label">检查中...</div>
      <div class="status-meta" id="status-meta"></div>
    </div>
    <span class="status-health err" id="status-health">--</span>
  </div>

  <div class="actions">
    <button class="btn btn-start" onclick="doAction('start')">
      <span class="icon">&#9654;</span> 启动
    </button>
    <button class="btn btn-stop" onclick="doAction('stop')">
      <span class="icon">&#9632;</span> 停止
    </button>
    <button class="btn btn-restart" onclick="doAction('restart')">
      <span class="icon">&#8635;</span> 重启
    </button>
    <button class="btn btn-kill" onclick="doAction('killport')">
      <span class="icon">&#9888;</span> 杀端口
    </button>
  </div>

  <div class="pages-title">工作台页面</div>
  <div class="pages">
    <a class="page-link" id="link-audit" href="#" target="_blank">
      <span class="dot" style="background:var(--blue)"></span>
      <span class="label">L0 字段审计</span>
      <span class="arrow">&rarr;</span>
    </a>
    <a class="page-link" id="link-ods" href="#" target="_blank">
      <span class="dot" style="background:var(--green)"></span>
      <span class="label">L1 ODS 标准化</span>
      <span class="arrow">&rarr;</span>
    </a>
    <a class="page-link" id="link-docs" href="#" target="_blank">
      <span class="dot" style="background:var(--purple)"></span>
      <span class="label">API 文档 (Swagger)</span>
      <span class="arrow">&rarr;</span>
    </a>
    <a class="page-link" id="link-health" href="#" target="_blank">
      <span class="dot" style="background:var(--orange)"></span>
      <span class="label">健康检查 API</span>
      <span class="arrow">&rarr;</span>
    </a>
  </div>

  <div class="log-panel">
    <div class="log-header">
      <span>服务日志</span>
      <small id="log-size"></small>
    </div>
    <div class="log-body" id="log-body">等待日志...</div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const POLL_MS = 3000;

function showToast(msg, ok) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + (ok ? 'ok' : 'err');
  setTimeout(() => t.className = 'toast', 3000);
}}

function colorLog(line) {{
  if (/error|exception|traceback/i.test(line)) return '<span class="err">' + esc(line) + '</span>';
  if (/warn/i.test(line)) return '<span class="warn">' + esc(line) + '</span>';
  if (/info/i.test(line)) return '<span class="info">' + esc(line) + '</span>';
  return esc(line);
}}

function esc(s) {{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function fmtBytes(b) {{ if (b < 1024) return b + ' B'; if (b < 1048576) return (b/1024).toFixed(1) + ' KB'; return (b/1048576).toFixed(1) + ' MB'; }}

async function refreshStatus() {{
  try {{
    const r = await fetch('/api/status');
    const d = await r.json();
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    const meta = document.getElementById('status-meta');
    const health = document.getElementById('status-health');

    if (d.running) {{
      dot.className = 'status-dot on';
      label.textContent = '运行中';
      meta.textContent = 'PID: ' + d.pid + '  |  端口: ' + d.port + '  |  运行时间: ' + (d.uptime || '?');
      health.className = 'status-health ' + (d.health ? 'ok' : 'err');
      health.textContent = d.health ? '健康' : '不可达';
    }} else {{
      dot.className = 'status-dot off';
      label.textContent = '已停止';
      meta.textContent = '后端服务未运行';
      health.className = 'status-health err';
      health.textContent = '离线';
    }}

    const logBody = document.getElementById('log-body');
    if (d.log_lines && d.log_lines.length > 0) {{
      logBody.innerHTML = d.log_lines.map(colorLog).join('\\n');
      logBody.scrollTop = logBody.scrollHeight;
    }} else {{
      logBody.textContent = '暂无日志。';
    }}
    document.getElementById('log-size').textContent = fmtBytes(d.log_size || 0);
  }} catch(e) {{ /* launcher loading */ }}
}}

async function doAction(action) {{
  const btns = document.querySelectorAll('.btn');
  btns.forEach(b => b.classList.add('loading'));
  try {{
    const r = await fetch('/api/' + action, {{ method: 'POST' }});
    const d = await r.json();
    showToast(d.msg, d.ok !== false);
  }} catch(e) {{
    showToast('请求失败: ' + e.message, false);
  }}
  btns.forEach(b => b.classList.remove('loading'));
  await refreshStatus();
}}

const base = window.location.protocol + '//' + window.location.hostname + ':{BACKEND_PORT}';
document.getElementById('link-audit').href = base + '/#audit';
document.getElementById('link-ods').href = base + '/#ods';
document.getElementById('link-docs').href = base + '/docs';
document.getElementById('link-health').href = base + '/api/v1/health';

refreshStatus();
setInterval(refreshStatus, POLL_MS);
</script>
</body>
</html>
"""


# ── Main ─────────────────────────────────────────────────────────────

class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True


def free_port(port):
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], stderr=subprocess.DEVNULL, text=True
        )
        for pid in out.strip().split("\n"):
            if pid.strip():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except OSError:
                    pass
        time.sleep(0.5)
    except Exception:
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LAUNCHER_PORT

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        s.close()
    except OSError:
        s.close()
        print(f"\n  端口 {port} 被占用，正在释放...")
        free_port(port)

    server = ReusableHTTPServer(("0.0.0.0", port), LauncherHandler)
    url = f"http://localhost:{port}/"
    print(f"\n  望优数仓工作台 rebuild2 — 启动器")
    print(f"  ────────────────────────────────")
    print(f"  启动器:  {url}")
    print(f"  后端:    http://localhost:{BACKEND_PORT}/ (启动后可用)")
    print(f"  数据库:  rebuild2 / rebuild2_meta schema")
    print(f"\n  Ctrl+C 停止启动器。\n")

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  启动器已停止。")
        server.server_close()
