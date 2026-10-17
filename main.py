from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

from landrop import __version__
from landrop import launcher
from landrop.errors import AppError
from landrop.runtime import InstanceGuard, RuntimeStore
from landrop.server import Server
from landrop.state import State
from landrop.ports import BAD_PORTS


def reopen(runtime_file: Path, args) -> bool:
    return launcher.reopen(runtime_file, args)


def bind_server(port: int, state: State, desktop=None):
    for attempt in range(20):
        try:
            server = Server(('0.0.0.0', port if attempt == 0 else 0), state, desktop)
        except OSError:
            continue
        if server.server_port in BAD_PORTS:
            server.server_close()
            continue
        return server
    raise AppError('暂时找不到可供浏览器访问的端口，请稍后重试。', 503, 'port-unavailable')


def run(args, data_dir: Path, runtime_file: Path):
    logging.basicConfig(filename=data_dir / 'errors.log', level=logging.WARNING, encoding='utf-8')
    state = State(data_dir, test_mode=args.test_data)
    state.cleanup_owned_partials()
    for path in args.share:
        if path.is_dir():
            state.add_folder(str(path))
        else:
            state.add_files([str(path)])
    desktop = None
    if not args.headless:
        from landrop.desktop import DesktopBridge
        desktop = DesktopBridge(state)
    runtime = RuntimeStore(runtime_file)
    server = None
    scanner = None
    serving = None
    try:
        server = bind_server(args.port, state, desktop)
        scanner = threading.Thread(target=state.scan_loop, daemon=True)
        scanner.start()
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        if desktop:
            desktop.prepare()
        runtime.write(state.port, state.admin_token)
        if sys.stdout:
            print(f'LanDrop {__version__} 已启动，端口 {state.port}。', flush=True)
        if desktop:
            desktop.run()
        else:
            while serving.is_alive() and not state.stopping.wait(.5):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        state.stopping.set()
        state.scan_requested.set()
        cleaned = True
        if server:
            if serving and serving.is_alive():
                cleaned = server.close_gracefully()
            else:
                server.server_close()
        if scanner:
            scanner.join(timeout=6)
        if desktop:
            desktop.close()
        runtime.remove_owned()
        if not cleaned:
            logging.warning('Some cancelled transfer workers did not finish before shutdown. Owned partial files will be cleaned on next startup.')


def main():
    parser = argparse.ArgumentParser(description='LanDrop：在局域网扫码传文件。')
    parser.add_argument('paths', type=Path, nargs='*', help='拖到 exe 图标上的文件或文件夹')
    parser.add_argument('--port', type=int, default=41421)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--no-browser', action='store_true', help='兼容旧参数；桌面版始终使用独立窗口')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--share', type=Path, action='append', default=[])
    parser.add_argument('--approve-upgrade', action='store_true', help='允许旧版本正常退出后启动新版')
    maintenance = parser.add_mutually_exclusive_group()
    maintenance.add_argument('--check-running', action='store_true', help='安装器检查；运行中返回 10')
    maintenance.add_argument('--prepare-upgrade', action='store_true', help='安装器请求正常退出，并等待进程结束')
    parser.add_argument('--test-data', action='store_true', help='标记合成文件验证；需要独立的 --state-dir')
    args = parser.parse_args()
    if args.test_data and args.state_dir is None:
        parser.error('测试模式需要独立的 --state-dir，避免使用日常数据。')
    if not 0 <= args.port <= 65535:
        parser.error('端口需要在 0 到 65535 之间。')
    if args.port in BAD_PORTS:
        parser.error('浏览器禁止访问这个端口，请使用默认端口或 --port 0。')
    args.share.extend(args.paths)
    data_dir = (args.state_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'LanDrop').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data_dir / 'errors.log', level=logging.WARNING, encoding='utf-8')
    runtime_file = data_dir / 'runtime.json'
    guard = InstanceGuard(data_dir)
    try:
        if args.check_running:
            return 10 if launcher.running(runtime_file) or not guard.acquire() else 0
        if args.prepare_upgrade:
            if launcher.running(runtime_file):
                launcher.stop_previous(runtime_file)
            until = time.monotonic() + 15
            while not guard.acquire() and time.monotonic() < until:
                time.sleep(.1)
            if not guard.acquire():
                raise AppError('程序尚未退出，请关闭系统文件选择窗口后重试。', 409, 'instance-busy')
            return 0
        guard.acquire()
        # Legacy headless copies do not own the instance lock. Always check
        # their runtime before starting a server, even when our lock succeeded.
        deadline = time.monotonic() + 15
        while True:
            stopping = False
            try:
                if reopen(runtime_file, args):
                    return
            except launcher.UpgradeRequired as upgrade:
                approved = args.approve_upgrade
                if not approved and not args.headless:
                    from landrop.desktop import confirm_upgrade
                    approved = confirm_upgrade(upgrade.running_version, __version__)
                if not approved:
                    if args.headless:
                        raise upgrade
                    return
                launcher.stop_previous(runtime_file)
            except launcher.InstanceStopping:
                stopping = True
            if not stopping and guard.acquire():
                break
            if time.monotonic() >= deadline:
                raise AppError('LanDrop尚未退出或启动尚未完成。请关闭系统文件选择窗口后重试。', 409, 'instance-busy')
            time.sleep(.1)
        run(args, data_dir, runtime_file)
    finally:
        guard.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.exception('Application failed')
        if getattr(sys, 'frozen', False) and '--headless' not in sys.argv:
            from landrop.desktop import show_error
            show_error('无法启动LanDrop。\n' + str(error))
        else:
            if sys.stderr:
                print(str(error), file=sys.stderr)
        raise SystemExit(1)
