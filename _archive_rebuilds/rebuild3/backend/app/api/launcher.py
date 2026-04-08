from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.common import SERVICE_REGISTRY, run_script, service_snapshot, tail_lines

router = APIRouter(prefix='/api/v1/launcher', tags=['launcher'])


@router.get('/services')
def get_services():
    services = [service_snapshot(key) for key in ('backend', 'frontend', 'database')]
    return {
        'status': 'ok',
        'services': services,
        'quick_actions': [
            './rebuild3/scripts/dev/start_all.sh',
            './rebuild3/scripts/dev/status.sh',
            './rebuild3/scripts/dev/stop_all.sh',
        ],
        'notes': [
            '后端当前由正在运行的 FastAPI 进程承载，因此启动器只提供状态检查和前端进程控制。',
            '数据库只做连通性检查，不在应用内执行 start/stop。',
            '状态为 port-open 表示端口已被占用，但不是当前 pid 文件管理的实例。',
            '如需完整重启，请优先使用 scripts/dev 下的 shell 脚本。',
        ],
    }


@router.get('/logs/{service_name}')
def get_service_logs(service_name: str, limit: int = Query(default=120, ge=10, le=500)):
    if service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=404, detail='未知服务')
    lines = tail_lines(SERVICE_REGISTRY[service_name].get('log_file'), limit=limit)
    return {
        'status': 'ok',
        'service': service_name,
        'lines': lines,
    }


@router.post('/services/{service_name}/{action}')
def manage_service(service_name: str, action: str):
    if service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=404, detail='未知服务')
    if action not in {'start', 'stop', 'restart'}:
        raise HTTPException(status_code=400, detail='仅支持 start / stop / restart')

    service = SERVICE_REGISTRY[service_name]
    if not service['supports_actions']:
        raise HTTPException(status_code=400, detail='当前服务不支持在启动器内直接控制')

    script_key = f'{action}_script'
    ok, output = run_script(service[script_key])
    if not ok:
        raise HTTPException(status_code=500, detail=output)

    return {
        'status': 'ok',
        'service': service_name,
        'action': action,
        'message': output,
        'snapshot': service_snapshot(service_name),
    }
