"""One bounded boot of the existing task-owned QA AVD; no settings or new AVD."""
from pathlib import Path
import os, time, json, subprocess, signal, shutil

ROOT = Path(__file__).resolve().parent
AVD = Path('/home/ai/.android/avd/pocket_verify_api35.avd')
ADB = '/home/ai/Android/Sdk/platform-tools/adb'
FLOOR = 4 * 1024**3
PEAK = 1_900_000_000

def allocated():
    return sum(p.stat().st_blocks * 512 for p in AVD.rglob('*') if p.is_file())

def device(*args):
    return subprocess.run([ADB, '-s', 'emulator-5620', *args], capture_output=True, text=True, timeout=8)

assert not (ROOT / 'boot-intent.json').exists()
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        argv = (proc / 'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError, PermissionError):
        continue
    assert not (b'-avd' in argv and b'pocket_verify_api35' in argv), 'Existing AVD process must be reconciled'
assert device('get-state').returncode != 0
baseline = json.loads((ROOT / 'resource-baseline.json').read_text())['free_before']
free = shutil.disk_usage(ROOT).free
assert free >= FLOOR + PEAK
base = allocated()
cmd = ['taskset', '-c', '2,3', '/home/ai/Android/Sdk/emulator/emulator', '-avd',
       'pocket_verify_api35', '-port', '5620', '-no-window', '-no-audio',
       '-no-snapshot', '-memory', '2048', '-cores', '2', '-gpu', 'swiftshader_indirect']
state = {'cmd': cmd, 'free_before': free, 'avd_allocated_before': base,
         'booted': False, 'shared_adb_and_other_devices_unchanged': True}
(ROOT / 'boot-intent.json').write_text(json.dumps(state, indent=2) + '\n')
with (ROOT / 'emulator.log').open('xb') as log:
    child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
state['pid'] = child.pid
state['startticks'] = Path(f'/proc/{child.pid}/stat').read_text().split()[21]
start = time.monotonic()
try:
    while time.monotonic() - start < 300:
        free = shutil.disk_usage(ROOT).free
        growth = allocated() - base
        state['peak_avd_growth_bytes'] = max(state.get('peak_avd_growth_bytes', 0), growth)
        state['min_free_bytes'] = min(state.get('min_free_bytes', free), free)
        assert free >= FLOOR and baseline - free <= PEAK
        assert growth <= 384 * 1024**2, 'Boot exceeds declared additional AVD allocation'
        assert (ROOT / 'emulator.log').stat().st_size <= 16 * 1024**2
        assert child.poll() is None, f'Emulator exited {child.returncode}'
        r = device('shell', 'getprop', 'sys.boot_completed')
        if r.returncode == 0 and r.stdout.strip() == '1':
            assert device('shell', 'getprop', 'ro.build.version.sdk').stdout.strip() == '35'
            assert device('emu', 'avd', 'name').stdout.splitlines()[0] == 'pocket_verify_api35'
            state['booted'] = True
            break
        time.sleep(2)
    assert state['booted'], 'Boot deadline exceeded'
except BaseException as exc:
    state['error'] = repr(exc)
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
    raise
finally:
    state['elapsed_seconds'] = time.monotonic() - start
    state['free_after'] = shutil.disk_usage(ROOT).free
    state['avd_allocated_after'] = allocated()
    (ROOT / 'boot-receipt.json').write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps(state, indent=2))
