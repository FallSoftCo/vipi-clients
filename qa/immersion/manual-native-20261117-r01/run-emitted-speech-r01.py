import hashlib
import json
import pathlib
import shutil
import subprocess
import time

root = pathlib.Path('/Users/Apple/Development/vipi-quality-20261117-r01/native-manual-provider-r01')
work = root / 'emitted-speech-r01'
work.mkdir(exist_ok=False)
receipt = {'started': time.time(), 'state': 'preparing', 'stages': [], 'sources': {}, 'signing': False, 'playback': False}

def save():
    (work / 'execution-r01.json').write_text(json.dumps(receipt, indent=2) + '\n')

def run(name, command, timeout):
    receipt['state'] = name
    save()
    started = time.time()
    with (work / (name + '.log')).open('x') as log:
        result = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    receipt['stages'].append({'name': name, 'command': command, 'exit': result.returncode, 'seconds': time.time() - started})
    save()
    if result.returncode:
        raise RuntimeError(name + ' failed')

try:
    assert shutil.disk_usage(root).free > 4_504_682_496 + 150 * 1024 * 1024
    sources = work / 'Sources/Probe'
    sources.mkdir(parents=True)
    for name in ['LocalSpeech.swift', 'SwahiliSpeech.swift', 'SpeechChunks.swift', 'EmittedSpeechProbe.swift']:
        data = (root / name).read_bytes()
        (sources / name).write_bytes(data)
        receipt['sources'][name] = hashlib.sha256(data).hexdigest()
    package = '/Users/Apple/Development/vipi-native-delivery-20261109-r01/app-build-r01/SourcePackages/checkouts/espeak-ng-spm'
    (work / 'Package.swift').write_text('// swift-tools-version: 6.2\nimport PackageDescription\nlet package = Package(name: "EmittedSpeechProbe", platforms: [.macOS(.v15)], dependencies: [.package(path: "' + package + '")], targets: [.executableTarget(name: "Probe", dependencies: [.product(name:"libespeak-ng", package:"espeak-ng-spm"), .product(name:"espeak-ng-data", package:"espeak-ng-spm")])])\n')
    run('build', ['swift', 'build', '-j', '2', '--disable-automatic-resolution'], 240)
    run('render', [str(work / '.build/debug/Probe'), str(work), str(root / 'results-r01.json')], 200)
    receipt['state'] = 'completed'
except BaseException as error:
    receipt['state'] = 'failed'
    receipt['error'] = repr(error)
finally:
    receipt['finished'] = time.time()
    receipt['free_after'] = shutil.disk_usage(root).free
    save()
    print(json.dumps(receipt))
