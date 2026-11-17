import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import os

root = Path('/Users/Apple/Development/vipi-quality-20261117-r01/native-manual-provider-r02')
receipt = root / 'execution-r02.json'
assert not receipt.exists(), 'Inspect original execution; never repeat an uncertain run'
assert shutil.disk_usage(root).free > 4_504_682_496 + 30 * 1024 * 1024
names = ['NativeContextProviderProbe.swift', 'ManualTranslation.swift', 'ManualTranslationContext.swift', 'ChineseFullReading.swift', 'JapaneseFullReading.swift', 'KoreanFullReading.swift', 'cases.json']
state = {'state': 'compiling', 'source_hashes': {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}, 'source_commit': '81b7a1b', 'stages': [], 'scope': 'Native local model calls using synthetic authored text only; no model preparation, signing, app or store actions'}
def save():
    receipt.write_text(json.dumps(state, indent=2) + '\n')
save()
try:
    commands = [
        ('compile', ['xcrun', 'swiftc', '-j2', '-target', 'arm64-apple-macos26.4', '-I', '../manual-translation', '-L', '../manual-translation', '-lVipiCore', 'ManualTranslation.swift', 'ManualTranslationContext.swift', 'ChineseFullReading.swift', 'JapaneseFullReading.swift', 'KoreanFullReading.swift', 'NativeContextProviderProbe.swift', '-o', 'native-context-provider']),
        ('run', ['./native-context-provider', str(root)])
    ]
    environment = dict(os.environ, DYLD_LIBRARY_PATH=str(root.parent/'manual-translation'))
    for label, command in commands:
        state['state'] = label
        save()
        with (root/(label+'-r02.log')).open('x') as log:
            result = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        state['stages'].append({'name': label, 'command': command, 'exit_code': result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(label+' failed')
    state['state'] = 'completed'
except BaseException as error:
    state['state'] = 'failed'
    state['error'] = repr(error)
finally:
    state['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
    print(json.dumps(state))
