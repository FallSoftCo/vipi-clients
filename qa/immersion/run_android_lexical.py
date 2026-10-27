#!/usr/bin/env python3
"""Run immutable lexical QA on Vipi's dedicated emulator, preserving payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import zipfile

ROOT = Path('/aosp/development/vipi')
APP = 'co.fallsoft.vipi'
ADB = ['/aosp/ozzz-android-toolchain/sdk/platform-tools/adb', '-s', 'emulator-5620']


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def shell(*args):
    return subprocess.check_output(ADB + ['shell', *args], text=True, stdin=subprocess.DEVNULL)


def ownsha(path):
    return subprocess.check_output(ADB + ['exec-out', 'run-as', APP, 'sha256sum', path], text=True).split()[0]


def put(source, target):
    with source.open('rb') as stream:
        subprocess.run(ADB + ['shell', '-T', shlex.join(['run-as', APP, 'sh', '-c', 'cat > ' + shlex.quote(target)])],
                       stdin=stream, check=True)
    assert ownsha(target) == sha(source)


def main(args):
    assert subprocess.check_output(['hostname'], text=True).strip() == 'ozzz-aosp'
    for value in (args.run, args.fixture, args.witness, args.shared_fixture):
        assert re.fullmatch('[0-9]{3}', value)
    assert 'vipi-api35-20261024' in subprocess.check_output(ADB + ['emu', 'avd', 'name'], text=True)
    if args.install:
        abi = shell('getprop', 'ro.product.cpu.abi').strip()
        with zipfile.ZipFile(ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk') as apk:
            packaged = {name.split('/')[1] for name in apk.namelist()
                        if name.startswith('lib/') and name.endswith('.so')}
        assert packaged == {abi}, 'Build dedicated QA with -PvipiQaAbi=' + abi
    artifacts = ROOT / 'artifacts'
    fixture = artifacts / ('lexical-qualification-' + args.fixture)
    manifest = json.loads((fixture / 'manifest.json').read_text())
    assert sha(fixture / 'cases.json') == manifest['cases_sha256']
    witness = artifacts / ('context-witnesses-' + args.witness) / 'witnesses.sqlite'
    metadata = json.loads((witness.parent / 'receipt.json').read_text())
    assert metadata['complete'] and sha(witness) == metadata['sha256']
    report_path = artifacts / ('lexical-coverage-android-' + args.run + '.json')
    log_path = artifacts / ('lexical-android-' + args.run + '.log')
    assert not report_path.exists() and not log_path.exists()
    receipt_path = artifacts / ('lexical-android-stage-' + args.run + '.json')
    assert not receipt_path.exists()
    receipt = dict(run=args.run, fixture=args.fixture, witness=args.witness,
                   witness_sha256=metadata['sha256'], temporary_shards=[], apks=[], complete=False)

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')

    save()
    shell('am', 'force-stop', APP)
    apks = [(APP, ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk'),
            (APP + '.test', ROOT / 'android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk')]
    if args.install:
        try:
            # The emulator is deliberately small. Release only checksum-matched
            # QA shards; the app's conversations, account and keys stay intact.
            for row in manifest['shards']:
                source = fixture / (row['language'] + '.sqlite')
                target = 'files/lexical-qualification-' + args.shared_fixture + '/' + source.name
                assert sha(source) == row['sha256'] == ownsha(target)
                entry = dict(language=row['language'], path=target, sha256=row['sha256'], removed=False, restored=False)
                receipt['temporary_shards'].append(entry)
                save()
                shell('run-as', APP, 'rm', target)
                entry['removed'] = True
                save()
            receipt['available_before_install'] = shell('df', '-k', '/data')
            save()
            with (artifacts / ('lexical-android-install-' + args.run + '.log')).open('x') as log:
                for _, apk in apks:
                    result = subprocess.run(ADB + ['install', '--no-streaming', '-r', str(apk)],
                                            capture_output=True, text=True, stdin=subprocess.DEVNULL)
                    log.write(result.stdout + result.stderr)
                    log.flush()
                    assert result.returncode == 0 and 'Success' in result.stdout, 'Installation failed; see retained log'
        finally:
            for row in receipt['temporary_shards']:
                if row['removed']:
                    put(fixture / (row['language'] + '.sqlite'), row['path'])
                    row['restored'] = True
                    save()
    for package, apk in apks:
        location = shell('pm', 'path', package).strip().removeprefix('package:')
        assert '\n' not in location and location.startswith('/data/app/')
        checksum = sha(apk)
        assert shell('sha256sum', location).split()[0] == checksum
        receipt['apks'].append(dict(package=package, sha256=checksum))
    remote = 'files/lexical-qualification-' + args.fixture
    shell('run-as', APP, 'mkdir', '-p', remote)
    for row in manifest['shards']:
        source = fixture / (row['language'] + '.sqlite')
        shared = 'files/lexical-qualification-' + args.shared_fixture + '/' + source.name
        assert ownsha(shared) == row['sha256']
        if args.fixture != args.shared_fixture:
            command = 'test -e ' + shlex.quote(remote + '/' + source.name)
            exists = subprocess.run(ADB + ['shell', shlex.join(['run-as', APP, 'sh', '-c', command])],
                                    stdin=subprocess.DEVNULL).returncode == 0
            if not exists:
                shell('run-as', APP, 'ln', '-s', '../lexical-qualification-' + args.shared_fixture + '/' + source.name,
                      remote + '/' + source.name)
            assert ownsha(remote + '/' + source.name) == row['sha256']
    for name in ('manifest.json', 'cases.json'):
        put(fixture / name, remote + '/' + name)
    remote_witness = 'files/context-witnesses-' + args.witness + '.sqlite'
    exists = subprocess.run(ADB + ['shell', 'run-as', APP, 'test', '-f', remote_witness],
                            stdin=subprocess.DEVNULL).returncode == 0
    if not exists:
        put(witness, remote_witness)
    assert ownsha(remote_witness) == metadata['sha256']
    receipt.update(complete=True, restored_shards_verified=True)
    save()
    with log_path.open('x') as log:
        subprocess.run(ADB + ['shell', 'am', 'instrument', '-w', '-r', '-e', 'vipiDedicatedEmulator', 'true',
            '-e', 'vipiLexicalRun', args.run, '-e', 'vipiLexicalFixture', args.fixture,
            '-e', 'vipiWitnessRevision', args.witness, '-e', 'vipiWitnessSha', metadata['sha256'],
            '-e', 'class', 'co.fallsoft.vipi.LexicalCoverageDeviceTest',
            APP + '.test/androidx.test.runner.AndroidJUnitRunner'], stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, check=True)
    raw = subprocess.check_output(ADB + ['exec-out', 'run-as', APP, 'cat', 'files/lexical-coverage-' + args.run + '.json'])
    report = json.loads(raw)
    assert report['run'] == args.run
    retained_path = report_path if report.get('complete') else report_path.with_name(report_path.stem + '-partial.json')
    with retained_path.open('xb') as stream:
        stream.write(raw)
    assert report.get('complete'), 'Incomplete native run; partial output is retained'
    print(json.dumps({k: report.get(k) for k in ['complete', 'passed', 'cases', 'failures']}))
    assert report['passed'], 'Native regressions failed; raw output is retained'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'fixture', 'witness'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--shared-fixture', default='009')
    parser.add_argument('--install', action='store_true')
    main(parser.parse_args())
