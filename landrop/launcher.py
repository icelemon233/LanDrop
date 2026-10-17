from __future__ import annotations

import http.cookiejar
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from . import __version__
from .errors import AppError
from .runtime import RuntimeStore
from .processes import ProcessWaiter


class UpgradeRequired(AppError):
    def __init__(self, running_version: str):
        super().__init__('旧版本正在运行，需要先正常退出后启动新版。', 409, 'upgrade-required')
        self.running_version = running_version


class InstanceStopping(AppError):
    def __init__(self):
        super().__init__('LanDrop正在退出，请稍候。', 409, 'instance-stopping')


def verify_instance(health, info):
    if not isinstance(health, dict) or health.get('app') != 'landrop' or (health.get('pid') is not None and info.pid and health['pid'] != info.pid):
        raise AppError('运行信息与当前端口不一致。请先在旧版界面退出LanDrop，再运行新版。', 409, 'runtime-mismatch')


def local_client():
    return build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))


def post(client, base: str, route: str, body: dict):
    request = Request(base + route, data=json.dumps(body).encode(), headers={'X-LanDrop': '1', 'Content-Type': 'application/json'})
    try:
        with client.open(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            problem = json.load(error)
        except (ValueError, OSError):
            problem = {}
        raise AppError(problem.get('error', '电脑端请求失败，请重试。'), error.code, problem.get('code', 'launch-rejected')) from error


def reopen(runtime_file: Path, args) -> bool:
    info = RuntimeStore(runtime_file).read()
    if info is None:
        return False
    client = local_client()
    base = f'http://127.0.0.1:{info.port}'
    try:
        with client.open(base + '/api/health', timeout=2) as response:
            health = json.load(response)
    except (URLError, TimeoutError, OSError):
        return False
    verify_instance(health, info)
    if health.get('phase') == 'stopping':
        raise InstanceStopping()
    if health.get('version') != __version__:
        raise UpgradeRequired(str(health.get('version', '未知版本')))
    activate = not getattr(args, 'headless', False)
    launched = post(client, base, '/api/desktop-launch', {'token': info.secret, 'activate': activate})
    launch_url = launched.get('url')
    if not isinstance(launch_url, str):
        raise AppError('电脑端启动响应不完整，请重新打开程序。', 502, 'launch-invalid')
    target = urlsplit(launch_url)
    if target.scheme != 'http' or target.netloc != f'127.0.0.1:{info.port}' or not target.path.startswith('/desktop/') or target.query or target.fragment:
        raise AppError('电脑端启动地址不正确，已停止打开浏览器。', 502, 'launch-invalid')
    if args.share:
        post(client, base, '/api/session', {'role': 'admin', 'token': info.secret})
        files = []
        for path in args.share:
            if path.is_dir():
                post(client, base, '/api/admin/add-folder', {'path': str(path.resolve())})
            else:
                files.append(str(path.resolve()))
        if files:
            post(client, base, '/api/admin/add-files', {'paths': files})
    if activate and launched.get('activated') is not True:
        raise AppError('桌面窗口未能恢复，请先正常退出 LanDrop，再重新打开。', 503, 'desktop-unavailable')
    return True


def stop_previous(runtime_file: Path):
    info = RuntimeStore(runtime_file).read()
    if info is None:
        return
    processes = ProcessWaiter(info.pid)
    try:
        client = local_client()
        base = f'http://127.0.0.1:{info.port}'
        with client.open(base + '/api/health', timeout=3) as response:
            health = json.load(response)
        verify_instance(health, info)
        if health.get('phase') != 'stopping':
            try:
                post(client, base, '/api/session', {'role': 'admin', 'token': info.secret})
                post(client, base, '/api/admin/shutdown', {})
            except AppError as error:
                if error.status == 401:
                    raise AppError('旧版端口对应的实例与运行凭据不一致。请先从旧版界面退出程序，再运行新版；文件和设置会保留。', 409, 'runtime-mismatch') from error
                raise
        if processes.handles:
            # Windows can deny opening a file while its owner deletes it.
            # Known process handles give a definitive exit result without
            # racing the runtime-file cleanup that happens during shutdown.
            processes.wait()
            return
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = RuntimeStore(runtime_file).read()
            if current is None or current.pid != info.pid:
                processes.wait()
                return
            time.sleep(.1)
        raise AppError('旧版尚未退出，请关闭系统文件选择窗口后重试。已有文件会保留。', 409, 'upgrade-pending')
    finally:
        processes.close()


def running(runtime_file: Path) -> bool:
    info = RuntimeStore(runtime_file).read()
    if info is None:
        return False
    try:
        with local_client().open(f'http://127.0.0.1:{info.port}/api/health', timeout=2) as response:
            health = json.load(response)
        return isinstance(health, dict) and health.get('app') == 'landrop'
    except (URLError, TimeoutError, OSError):
        return False
