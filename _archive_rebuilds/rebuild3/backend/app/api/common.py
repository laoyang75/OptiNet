from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import json
from pathlib import Path
import os
import socket
from threading import RLock
import time
import subprocess
from typing import Any

from psycopg.rows import dict_row

from app.core.database import get_conn

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = PROJECT_ROOT / 'docs'
RUNTIME_ROOT = PROJECT_ROOT / 'runtime'
SPIKE_ARCHIVE_ROOT = PROJECT_ROOT / 'archive' / '20260404_ui_spike'

OPERATOR_NAME_MAP = {
    '46000': '中国移动',
    '46001': '中国联通',
    '46011': '中国电信',
    '46015': '中国广电',
}

LIFECYCLE_LABELS = {
    'waiting': '等待',
    'observing': '观察',
    'active': '活跃',
    'dormant': '休眠',
    'retired': '退役',
    'rejected': '拒收',
}

HEALTH_LABELS = {
    'healthy': '健康',
    'insufficient': '数据不足',
    'gps_bias': 'GPS 偏差',
    'collision_suspect': '碰撞嫌疑',
    'collision_confirmed': '碰撞确认',
    'dynamic': '动态',
    'migration_suspect': '迁移嫌疑',
}

ISSUE_HEALTH_STATES = {
    'gps_bias',
    'collision_suspect',
    'collision_confirmed',
    'dynamic',
    'migration_suspect',
}

SERVICE_REGISTRY = {
    'backend': {
        'name': '后端 API',
        'tech': 'FastAPI · Python',
        'host': '127.0.0.1',
        'port': int(os.environ.get('REBUILD3_BACKEND_PORT', '47121')),
        'pid_file': PROJECT_ROOT / 'runtime' / 'backend.pid',
        'log_file': PROJECT_ROOT / 'runtime' / 'backend.log',
        'start_script': PROJECT_ROOT / 'scripts' / 'dev' / 'start_backend.sh',
        'stop_script': PROJECT_ROOT / 'scripts' / 'dev' / 'stop_backend.sh',
        'restart_script': PROJECT_ROOT / 'scripts' / 'dev' / 'restart_backend.sh',
        'supports_actions': False,
    },
    'frontend': {
        'name': '前端开发服务',
        'tech': 'Vue 3 · Vite',
        'host': '127.0.0.1',
        'port': int(os.environ.get('REBUILD3_FRONTEND_PORT', '47122')),
        'pid_file': PROJECT_ROOT / 'runtime' / 'frontend.pid',
        'log_file': PROJECT_ROOT / 'runtime' / 'frontend.log',
        'start_script': PROJECT_ROOT / 'scripts' / 'dev' / 'start_frontend.sh',
        'stop_script': PROJECT_ROOT / 'scripts' / 'dev' / 'stop_frontend.sh',
        'restart_script': PROJECT_ROOT / 'scripts' / 'dev' / 'restart_frontend.sh',
        'supports_actions': True,
    },
    'database': {
        'name': '数据库',
        'tech': 'PostgreSQL 17',
        'host': os.environ.get('REBUILD3_PG_HOST', '192.168.200.217'),
        'port': int(os.environ.get('REBUILD3_PG_PORT', '5433')),
        'pid_file': None,
        'log_file': None,
        'start_script': None,
        'stop_script': None,
        'restart_script': None,
        'supports_actions': False,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or {})
            return [dict(row) for row in cur.fetchall()]


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = fetch_all(sql, params)
    return rows[0] if rows else {}


def ttl_cache(ttl_seconds: int):
    cache: dict[str, tuple[float, Any]] = {}
    lock = RLock()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True, default=str, ensure_ascii=False)
            now = time.monotonic()
            with lock:
                cached = cache.get(key)
                if cached and cached[0] > now:
                    return cached[1]
            result = func(*args, **kwargs)
            with lock:
                cache[key] = (now + ttl_seconds, result)
            return result

        return wrapper

    return decorator


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any) -> bool:
    return bool(value)


def operator_name(operator_code: str | None) -> str:
    if not operator_code:
        return '未知运营商'
    return OPERATOR_NAME_MAP.get(operator_code, operator_code)


def lifecycle_label(value: str | None) -> str:
    return LIFECYCLE_LABELS.get(value or '', value or '未知')


def health_label(value: str | None) -> str:
    return HEALTH_LABELS.get(value or '', value or '未知')


def compare_membership(r3_value: bool, r2_value: bool) -> str:
    if r3_value and not r2_value:
        return 'r3_only'
    if r2_value and not r3_value:
        return 'r2_only'
    return 'aligned'


def compare_label(value: str) -> str:
    return {
        'aligned': '口径对齐',
        'r3_only': '仅 rebuild3',
        'r2_only': '仅 rebuild2',
    }.get(value, value)


def watch_flag(lifecycle_state: str | None, health_state: str | None) -> bool:
    return lifecycle_state == 'active' and (health_state or 'healthy') != 'healthy'


def format_window(start: Any, end: Any) -> str:
    if not start or not end:
        return '未提供窗口'
    return f'{str(start)[:16]} ~ {str(end)[:16]}'


def port_open(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def pid_alive(pid_file: Path | None) -> int | None:
    if not pid_file or not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def tail_lines(log_file: Path | None, limit: int = 120) -> list[str]:
    if not log_file or not log_file.exists():
        return []
    lines = log_file.read_text(errors='ignore').splitlines()
    return lines[-limit:]


def run_script(script_path: Path) -> tuple[bool, str]:
    if not script_path.exists():
        return False, f'脚本不存在：{script_path}'
    completed = subprocess.run(
        [str(script_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = (completed.stdout or completed.stderr or '').strip()
    if completed.returncode != 0:
        return False, output or f'执行失败：{script_path.name}'
    return True, output or 'ok'


def service_snapshot(service_key: str) -> dict[str, Any]:
    service = SERVICE_REGISTRY[service_key]
    pid = pid_alive(service.get('pid_file'))
    port_busy = port_open(service['host'], service['port'])

    if service_key == 'database':
        status = 'running' if port_busy else 'stopped'
    elif pid is not None and port_busy:
        status = 'running'
    elif pid is not None:
        status = 'process-only'
    elif port_busy:
        status = 'port-open'
    else:
        status = 'stopped'

    if service_key == 'backend' and status == 'running':
        hint = '当前请求所在进程即后端服务；控制操作请使用启动脚本。'
    elif status == 'port-open':
        hint = '端口已被其他进程占用，当前脚本不会把它视为可控运行实例。'
    elif status == 'process-only':
        hint = '检测到脚本管理进程，但端口尚未就绪；请检查 runtime 日志。'
    elif service['supports_actions']:
        hint = '可在启动器中执行 start / stop / restart。'
    else:
        hint = '当前仅提供状态检查与命令提示。'
    return {
        'service_key': service_key,
        'name': service['name'],
        'tech': service['tech'],
        'host': service['host'],
        'port': service['port'],
        'pid': pid,
        'status': status,
        'uptime': 'running' if status == 'running' else None,
        'supports_actions': service['supports_actions'],
        'command_hint': {
            'start': str(service['start_script']) if service.get('start_script') else None,
            'stop': str(service['stop_script']) if service.get('stop_script') else None,
            'restart': str(service['restart_script']) if service.get('restart_script') else None,
        },
        'hint': hint,
    }
