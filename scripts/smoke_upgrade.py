"""Run real old/new Windows binaries through native and headless upgrades."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from landrop import __version__
from landrop.launcher import local_client,post,stop_previous
from landrop.runtime import RuntimeStore
from landrop.errors import AppError

parser=argparse.ArgumentParser()
parser.add_argument('--old',type=Path,required=True)
parser.add_argument('--new',type=Path,required=True)
parser.add_argument('--work',type=Path,required=True)
parser.add_argument('--interactive',action='store_true')
args=parser.parse_args()
work=args.work.resolve()
if not work.is_relative_to(root.parent) or work.exists():
    raise SystemExit('Use a fresh upgrade test directory inside work/.')
work.mkdir(parents=True)
flags=subprocess.CREATE_NO_WINDOW

def runtime_info(path):
    deadline = time.monotonic() + 5
    while True:
        try:
            return RuntimeStore(path).read()
        except AppError as error:
            if error.code != 'runtime-unreadable' or not isinstance(error.__cause__, PermissionError) or time.monotonic() >= deadline:
                raise
            # Windows can briefly deny reads while the previous owner removes its file.
            time.sleep(.05)

def wait_until(predicate,processes,timeout=30):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        result=predicate()
        if result:
            return result
        if any(process.poll() is not None for process in processes):
            raise RuntimeError('A test process exited before its expected state.')
        time.sleep(.1)
    raise RuntimeError('Upgrade test did not reach its expected state.')

results=[]

def assert_preserved_settings(path, original):
    before = json.loads(original)
    after = json.loads(path.read_bytes())
    assert set(after) == set(before)
    assert {key: value for key, value in after.items() if key != 'preferences'} == {key: value for key, value in before.items() if key != 'preferences'}
    old_preferences = before.get('preferences', {})
    preferences = after.get('preferences', {})
    assert all(preferences.get(key) == value for key, value in old_preferences.items())
    # A desktop launch may migrate appearance into the server's saved UI preferences.
    assert set(preferences) - set(old_preferences) <= {'windowTheme', 'windowCloseBehavior', 'trayNoticeSeen'}

for mode in ('native','headless'):
    data=work/mode
    data.mkdir()
    received=data/'收到的文件'
    received.mkdir()
    (received/'keep.txt').write_bytes(b'preserve received data')
    shared=work/(mode+'.apk')
    shared.write_bytes(b'synthetic build')
    runtime=data/'runtime.json'
    record=data/'launch.txt'
    helper=work/'capture.py'
    helper.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(sys.argv[2], 'utf-8')\n",'utf-8')
    environment={**os.environ,'BROWSER':f'"{sys.executable}" "{helper}" "{record}" %s'}
    old=subprocess.Popen([str(args.old.resolve()),'--state-dir',str(data),'--port','0','--no-browser','--share',str(shared),*(['--headless'] if mode=='headless' else [])],creationflags=flags)
    new=None
    try:
        old_info=wait_until(lambda:runtime_info(runtime),[old])
        settings=(data/'settings.json').read_bytes()
        new_command=[str(args.new.resolve()),'--state-dir',str(data),'--port',str(old_info.port),'--test-data']
        if not args.interactive or mode!='native':
            new_command.append('--approve-upgrade')
        new=subprocess.Popen(new_command,env=environment,creationflags=flags)
        print(json.dumps({'phase':'upgrade-started','mode':mode,'interactive':args.interactive and mode=='native'}),flush=True)
        def ready():
            info=runtime_info(runtime)
            return info if info and info.version==__version__ and info.pid!=old_info.pid and (data/'desktop-observation.json').exists() else None
        new_info=wait_until(ready,[new],timeout=55 if args.interactive else 30)
        old.wait(timeout=15)
        assert not record.exists(), 'Upgrade opened an external browser'
        observation=json.loads((data/'desktop-observation.json').read_text('utf-8'))
        assert observation['role']=='admin' and observation['phase']=='connected'
        browser=local_client()
        launch_url=post(browser,f'http://127.0.0.1:{new_info.port}','/api/desktop-launch',{'token':new_info.secret})['url']
        with browser.open(launch_url,timeout=5) as response:
            assert response.url.endswith('/desktop')
        with browser.open(f'http://127.0.0.1:{new_info.port}/api/state') as response:
            state=json.load(response)
        assert state['role']=='admin' and state['version']==__version__
        assert any(item['name']==shared.name for item in state['files'])
        assert_preserved_settings(data/'settings.json', settings)
        assert (received/'keep.txt').read_bytes()==b'preserve received data'
        results.append(mode+' old copy -> independent Windows window; authenticated embedded UI, no external browser, shares and received data preserved')
    finally:
        if runtime_info(runtime):
            stop_previous(runtime)
        old.wait(timeout=15)
        if new:
            new.wait(timeout=15)

# Two independent app data directories must authenticate against separate ports.
first_data,second_data=work/'first',work/'second'
first=subprocess.Popen([str(args.old.resolve()),'--headless','--no-browser','--port','0','--state-dir',str(first_data)],creationflags=flags)
second=None
try:
    first_info=wait_until(lambda:runtime_info(first_data/'runtime.json'),[first])
    second=subprocess.Popen([str(args.new.resolve()),'--headless','--no-browser','--port',str(first_info.port),'--state-dir',str(second_data)],creationflags=flags)
    second_info=wait_until(lambda:runtime_info(second_data/'runtime.json'),[second])
    assert first_info.port!=second_info.port
    for info in (first_info,second_info):
        client=local_client()
        post(client,f'http://127.0.0.1:{info.port}','/api/session',{'role':'admin','token':info.secret})
    results.append('independent data directories use separate ports and credentials')
finally:
    for directory,process in ((second_data,second),(first_data,first)):
        if process:
            if runtime_info(directory/'runtime.json'):
                stop_previous(directory/'runtime.json')
            process.wait(timeout=15)
report={'version':__version__,'passed':results,'interactiveConfirmation':args.interactive,'payloadSha256':hashlib.sha256(args.new.read_bytes()).hexdigest()}
(work/'upgrade-validation.json').write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report,indent=2),flush=True)
