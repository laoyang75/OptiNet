#!/usr/bin/env python3
"""rebuild4 流式治理工作台 - 独立启动器

独立运维入口，不依赖主系统前后端。
通过 WebSocket 和 REST API 提供服务控制、状态检查和日志查看。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = Path(__file__).resolve().parent / 'launcher_ui'
RUNTIME_ROOT = PROJECT_ROOT / 'runtime'

LAUNCHER_HOST = os.environ.get('REBUILD4_LAUNCHER_HOST', '127.0.0.1')
LAUNCHER_PORT = int(os.environ.get('REBUILD4_LAUNCHER_PORT', '57130'))
BACKEND_HOST = os.environ.get('REBUILD4_BACKEND_HOST', '127.0.0.1')
BACKEND_PORT = int(os.environ.get('REBUILD4_BACKEND_PORT', '57131'))
FRONTEND_HOST = os.environ.get('REBUILD4_FRONTEND_HOST', '127.0.0.1')
FRONTEND_PORT = int(os.environ.get('REBUILD4_FRONTEND_PORT', '57132'))
DB_HOST = os.environ.get('REBUILD4_PG_HOST', '192.168.200.217')
DB_PORT = int(os.environ.get('REBUILD4_PG_PORT', '5433'))


@dataclass(frozen=True)
class ServiceSpec:
    key: str
    name: str
    tech: str
    host: str
    port: int
    pid_file: Path | None
    log_file: Path | None
    start_script: Path | None
    stop_script: Path | None
    restart_script: Path | None
    supports_actions: bool
    supports_kill: bool
    note: str


SERVICE_REGISTRY: dict[str, ServiceSpec] = {
    'backend': ServiceSpec(
        key='backend',
        name='后端 API',
        tech='FastAPI · Python',
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        pid_file=RUNTIME_ROOT / 'backend.pid',
        log_file=RUNTIME_ROOT / 'backend.log',
        start_script=PROJECT_ROOT / 'scripts' / 'dev' / 'start_backend.sh',
        stop_script=PROJECT_ROOT / 'scripts' / 'dev' / 'stop_backend.sh',
        restart_script=PROJECT_ROOT / 'scripts' / 'dev' / 'restart_backend.sh',
        supports_actions=True,
        supports_kill=True,
        note='rebuild4 正式读模型 API 服务。',
    ),
    'frontend': ServiceSpec(
        key='frontend',
        name='前端工作台',
        tech='Vue 3 · Vite',
        host=FRONTEND_HOST,
        port=FRONTEND_PORT,
        pid_file=RUNTIME_ROOT / 'frontend.pid',
        log_file=RUNTIME_ROOT / 'frontend.log',
        start_script=PROJECT_ROOT / 'scripts' / 'dev' / 'start_frontend.sh',
        stop_script=PROJECT_ROOT / 'scripts' / 'dev' / 'stop_frontend.sh',
        restart_script=PROJECT_ROOT / 'scripts' / 'dev' / 'restart_frontend.sh',
        supports_actions=True,
        supports_kill=True,
        note='rebuild4 流式治理工作台 dev server。',
    ),
    'database': ServiceSpec(
        key='database',
        name='数据库',
        tech='PostgreSQL 17',
        host=DB_HOST,
        port=DB_PORT,
        pid_file=None,
        log_file=None,
        start_script=None,
        stop_script=None,
        restart_script=None,
        supports_actions=False,
        supports_kill=False,
        note='远端只读输入源，仅做连通性检查。',
    ),
}

LOG_TS_PATTERN = re.compile(r'^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s*(?P<rest>.*)$')


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def now_display() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def is_local_host(host: str) -> bool:
    return host in {'127.0.0.1', 'localhost', '0.0.0.0'}


def pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(pid_file: Path | None) -> int | None:
    if not pid_file or not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return None
    if not pid_alive(pid):
        pid_file.unlink(missing_ok=True)
        return None
    return pid


def port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def get_uptime(pid: int | None) -> str | None:
    if pid is None:
        return None
    try:
        output = subprocess.check_output(['ps', '-o', 'etime=', '-p', str(pid)], text=True)
    except Exception:
        return None
    return output.strip() or None


def tail_lines(path: Path | None, limit: int) -> list[str]:
    if not path or not path.exists():
        return []
    return path.read_text(errors='ignore').splitlines()[-limit:]


def detect_level(line: str) -> str:
    lowered = line.lower()
    if any(token in lowered for token in ('error', 'exception', 'traceback', 'fatal', 'failed')):
        return 'error'
    if any(token in lowered for token in ('warn', 'warning', 'occupied', 'retry', 'slow')):
        return 'warn'
    return 'info'


def parse_log_line(line: str) -> dict[str, str]:
    stripped = line.strip()
    if not stripped:
        return {'ts': '', 'level': 'info', 'msg': ''}
    match = LOG_TS_PATTERN.match(stripped)
    ts = ''
    message = stripped
    if match:
        ts = match.group('ts').replace('T', ' ')
        message = match.group('rest').strip() or stripped
    return {'ts': ts, 'level': detect_level(message), 'msg': message}


def backend_health() -> dict[str, Any] | None:
    try:
        with urlopen(f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/health', timeout=0.5) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None


def service_snapshot(service_key: str) -> dict[str, Any]:
    service = SERVICE_REGISTRY[service_key]
    pid = read_pid(service.pid_file)
    port_busy = port_open(service.host, service.port)

    if service.key == 'database':
        status = 'running' if port_busy else 'stopped'
    elif pid and port_busy:
        status = 'running'
    elif pid:
        status = 'starting'
    elif port_busy:
        status = 'port-open'
    else:
        status = 'stopped'

    if service.key == 'database' and status == 'running':
        hint = '远端数据库可达，当前只提供连通性检查。'
    elif status == 'running':
        hint = '由 rebuild4 脚本托管的实例已在线。'
    elif status == 'starting':
        hint = '检测到脚本管理进程，但端口尚未就绪。'
    elif status == 'port-open':
        hint = '端口已被外部进程占用，请先确认冲突来源。'
    elif service.supports_actions:
        hint = '可直接在启动器中执行启动、停止和重启。'
    else:
        hint = service.note

    snapshot = {
        'service_key': service.key,
        'name': service.name,
        'tech': service.tech,
        'host': service.host,
        'port': service.port,
        'pid': pid,
        'uptime': get_uptime(pid),
        'status': status,
        'supports_actions': service.supports_actions,
        'supports_kill': service.supports_kill and is_local_host(service.host),
        'hint': hint,
        'note': service.note,
        'log_path': str(service.log_file) if service.log_file else None,
        'links': {
            'service_url': f'http://{service.host}:{service.port}' if is_local_host(service.host) else None,
            'health_url': f'http://{service.host}:{service.port}/api/health' if service.key == 'backend' else None,
        },
    }
    if service.key == 'backend' and status == 'running':
        snapshot['health'] = backend_health()
    return snapshot


def service_logs(service_key: str, limit: int) -> list[dict[str, str]]:
    service = SERVICE_REGISTRY[service_key]
    lines = tail_lines(service.log_file, limit)
    if not lines:
        if service.key == 'database':
            lines = [f'{now_display()} INFO  当前数据库仅做连通性检查，未接本地日志文件。']
        else:
            snapshot = service_snapshot(service_key)
            if snapshot['status'] == 'stopped':
                lines = [f'{now_display()} INFO  服务尚未启动，暂无日志。']
            elif snapshot['status'] == 'port-open':
                lines = [f'{now_display()} WARN  端口已被外部进程占用，本地 runtime 日志不可用。']
    return [parse_log_line(line) for line in lines][-limit:]


def run_script(script: Path | None) -> tuple[bool, str]:
    if script is None:
        return False, '当前服务没有配置可执行脚本'
    if not script.exists():
        return False, f'脚本不存在：{script}'
    completed = subprocess.run(
        [str(script)], cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=90,
    )
    output = '\n'.join(part for part in ((completed.stdout or '').strip(), (completed.stderr or '').strip()) if part).strip()
    if completed.returncode != 0:
        return False, output or f'{script.name} 执行失败'
    return True, output or 'ok'


def kill_local_port(service_key: str) -> tuple[bool, str]:
    service = SERVICE_REGISTRY[service_key]
    if not service.supports_kill or not is_local_host(service.host):
        return False, '当前服务不支持 kill-port'
    try:
        output = subprocess.check_output(['lsof', '-ti', f':{service.port}'], text=True, stderr=subprocess.DEVNULL)
        pids = [int(item) for item in output.splitlines() if item.strip()]
    except subprocess.CalledProcessError:
        pids = []
    if not pids:
        return True, f'端口 {service.port} 当前空闲'
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 3
    while time.time() < deadline and port_open(service.host, service.port):
        time.sleep(0.2)
    if port_open(service.host, service.port):
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    if service.pid_file:
        service.pid_file.unlink(missing_ok=True)
    return True, f'已释放端口 {service.port}（处理 {len(pids)} 个进程）'


def handle_service_action(service_key: str, action: str) -> dict[str, Any]:
    if service_key not in SERVICE_REGISTRY:
        raise KeyError('未知服务')
    service = SERVICE_REGISTRY[service_key]
    if action == 'kill-port':
        ok, message = kill_local_port(service_key)
    else:
        if not service.supports_actions:
            return {
                'status': 'error', 'service': service_key, 'action': action,
                'message': '当前服务仅支持状态检查，不支持直接控制。',
                'snapshot': service_snapshot(service_key),
            }
        script = {'start': service.start_script, 'stop': service.stop_script, 'restart': service.restart_script}.get(action)
        if script is None:
            return {
                'status': 'error', 'service': service_key, 'action': action,
                'message': f'不支持操作：{action}', 'snapshot': service_snapshot(service_key),
            }
        ok, message = run_script(script)
    return {
        'status': 'ok' if ok else 'error', 'service': service_key,
        'action': action, 'message': message, 'snapshot': service_snapshot(service_key),
    }


def handle_all_action(action: str) -> dict[str, Any]:
    if action not in {'start', 'stop', 'restart'}:
        return {'status': 'error', 'message': f'不支持操作：{action}', 'results': []}
    if action == 'start':
        results = [handle_service_action(n, 'start') for n in ['backend', 'frontend']]
    elif action == 'stop':
        results = [handle_service_action(n, 'stop') for n in ['frontend', 'backend']]
    else:
        results = [handle_service_action(n, 'stop') for n in ['frontend', 'backend']]
        results += [handle_service_action(n, 'start') for n in ['backend', 'frontend']]
    return {
        'status': 'ok' if all(r['status'] == 'ok' for r in results) else 'error',
        'action': action, 'message': f'批量操作完成：{action}', 'results': results,
        'services': [service_snapshot(n) for n in SERVICE_REGISTRY],
    }


def launcher_payload(host: str, port: int) -> dict[str, Any]:
    service_names = ('backend', 'frontend', 'database')
    snapshots: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(service_snapshot, name): name for name in service_names}
        for future in as_completed(futures):
            name = futures[future]
            snapshots[name] = future.result()
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'launcher': {'host': host, 'port': port, 'url': f'http://{host}:{port}'},
        'quick_links': {
            'workbench': f'http://{FRONTEND_HOST}:{FRONTEND_PORT}',
            'backend_health': f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/health',
        },
        'services': [snapshots[name] for name in service_names],
    }


class LauncherHandler(BaseHTTPRequestHandler):
    server_version = 'rebuild4-launcher/1.0'

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in {'/', '/index.html'}:
            self._send_file(UI_ROOT / 'index.html', 'text/html; charset=utf-8')
            return
        if path == '/api/launcher/services':
            self._send_json(launcher_payload(*self.server.server_address))
            return
        if path.startswith('/api/launcher/logs/'):
            service_key = unquote(path.removeprefix('/api/launcher/logs/'))
            if service_key not in SERVICE_REGISTRY:
                self._send_json({'status': 'error', 'message': '未知服务'}, HTTPStatus.NOT_FOUND)
                return
            limit = max(20, min(500, int(query.get('limit', ['200'])[0])))
            self._send_json({
                'status': 'ok', 'generated_at': now_iso(),
                'service': service_key,
                'lines': service_logs(service_key, limit),
                'snapshot': service_snapshot(service_key),
            })
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/launcher/services/all/'):
            action = path.removeprefix('/api/launcher/services/all/')
            self._send_json(handle_all_action(action), HTTPStatus.OK)
            return
        if path.startswith('/api/launcher/services/'):
            suffix = path.removeprefix('/api/launcher/services/')
            parts = [p for p in suffix.split('/') if p]
            if len(parts) != 2:
                self._send_json({'status': 'error', 'message': '非法路径'}, HTTPStatus.BAD_REQUEST)
                return
            service_key, action = parts
            if service_key not in SERVICE_REGISTRY:
                self._send_json({'status': 'error', 'message': '未知服务'}, HTTPStatus.NOT_FOUND)
                return
            result = handle_service_action(service_key, action)
            status = HTTPStatus.OK if result['status'] == 'ok' else HTTPStatus.BAD_REQUEST
            self._send_json(result, status)
            return
        self.send_error(HTTPStatus.NOT_FOUND)


# ---------------------------------------------------------------------------
# 端口冲突诊断辅助
# ---------------------------------------------------------------------------

def find_port_occupants(port: int) -> list[int]:
    """返回占用指定端口的所有进程 PID 列表。"""
    try:
        output = subprocess.check_output(
            ['lsof', '-ti', f':{port}'], text=True, stderr=subprocess.DEVNULL
        )
        return [int(p) for p in output.splitlines() if p.strip()]
    except subprocess.CalledProcessError:
        return []


def describe_pid(pid: int) -> str:
    """返回进程的 PID + 命令行摘要，用于显示给用户。"""
    try:
        line = subprocess.check_output(
            ['ps', '-o', 'pid=,comm=,args=', '-p', str(pid)],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return line if line else str(pid)
    except Exception:
        return str(pid)


def kill_pids_gracefully(pids: list[int]) -> None:
    """先 SIGTERM，等 3 秒，仍存活则 SIGKILL。"""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not any(pid_alive(p) for p in pids):
            break
        time.sleep(0.2)
    for pid in pids:
        if pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description='rebuild4 独立启动器')
    parser.add_argument('--host', default=LAUNCHER_HOST)
    parser.add_argument('--port', default=LAUNCHER_PORT, type=int)
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    parser.add_argument('--kill-port', action='store_true',
                        help='端口被占用时自动终止占用进程（非交互模式）')
    args = parser.parse_args()

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    server = None
    for attempt in range(2):
        try:
            server = ThreadingHTTPServer((args.host, args.port), LauncherHandler)
            break  # 绑定成功
        except OSError:
            pids = find_port_occupants(args.port)
            print(f'\n  ⚠️  端口 {args.port} 已被占用')
            if pids:
                print('  占用进程：')
                for pid in pids:
                    print(f'    · PID {pid}  {describe_pid(pid)}')
            else:
                print('  （无法通过 lsof 识别占用进程，可能需要 root 权限）')

            if attempt > 0:
                print(f'\n  ❌ 仍无法绑定端口 {args.port}，请手动处理后重试。')
                return

            # 决定是否杀掉
            if args.kill_port:
                do_kill = True
            else:
                print()
                try:
                    ans = input('  是否终止以上进程并重新启动？[y/N]: ').strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = 'n'
                do_kill = (ans == 'y')

            if do_kill:
                if pids:
                    kill_pids_gracefully(pids)
                    time.sleep(0.4)
                    print(f'  ✓ 进程已终止，正在重新绑定端口 {args.port}...')
                else:
                    print(f'  ❌ 没有可终止的进程，请手动释放端口 {args.port}。')
                    return
            else:
                print(f'\n  提示：可使用 --port <端口号> 指定其他端口，')
                print(f'  或添加 --kill-port 参数下次自动处理。')
                return

    if server is None:
        return

    url = f'http://{args.host}:{args.port}'
    print(f'\n  rebuild4 流式治理工作台 - 独立启动器')
    print(f'  启动器:  {url}')
    print(f'  后端:    http://{BACKEND_HOST}:{BACKEND_PORT}')
    print(f'  前端:    http://{FRONTEND_HOST}:{FRONTEND_PORT}')
    print(f'  数据库:  {DB_HOST}:{DB_PORT}')
    print(f'\n  Ctrl+C 停止启动器。\n')

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  启动器已停止。')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
