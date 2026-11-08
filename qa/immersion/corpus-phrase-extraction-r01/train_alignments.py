#!/usr/bin/env python3
"""Run the pinned five-iteration aligner and two symmetrization controls once."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from extract_pgv import OUT, HERE, sha, write


def main():
    training = json.loads((OUT / 'training-receipt.json').read_text())
    assert training['complete']
    protocol = json.loads((HERE / 'protocol.json').read_text())
    target = OUT / 'alignments'
    target.mkdir(exist_ok=False)
    tool = OUT / 'toolchain'
    build = json.loads((tool / 'build-receipt.json').read_text())
    for name, digest in build['binary_sha256'].items():
        assert sha(tool / name) == digest
    commands = []
    for row in training['pairs']:
        pair = row['pair']
        for artifact in row['artifacts']:
            assert sha(Path(artifact['path'])) == artifact['sha256']
        for direction in ['forward', 'reverse']:
            stem = f'{pair}-{direction}'
            cmd = [str(tool/'fast_align'), '-i', str(OUT/(pair+'.txt')), '-d', '-o', '-v', '-I', '5', '-p', str(target/(stem+'.params'))]
            if direction == 'reverse':
                cmd.append('-r')
            commands.append(dict(kind='alignment', pair=pair, direction=direction, command=cmd, output=str(target/(stem+'.align')), log=str(target/(stem+'.log'))))
        for arm in ['intersect', 'grow-diag-final-and']:
            commands.append(dict(kind='symmetrization', pair=pair, arm=arm, command=[str(tool/'atools'), '-i', str(target/(pair+'-forward.align')), '-j', str(target/(pair+'-reverse.align')), '-c', arm], output=str(target/(pair+'-'+arm+'.align')), log=str(target/(pair+'-'+arm+'.log'))))
    freeze = dict(production=False, compiler_sha256=sha(Path(__file__)), training_receipt_sha256=sha(OUT/'training-receipt.json'), toolchain_build_receipt_sha256=sha(tool/'build-receipt.json'), commands=commands, concurrency=1, threads_per_process=1, free_bytes=shutil.disk_usage(OUT).free)
    (target/'execution-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    assert freeze['free_bytes'] > protocol['resources']['minimum_free_disk_bytes'] + 512 * 1024 ** 2
    started = time.monotonic()
    receipt = dict(complete=False, freeze_sha256=sha(target/'execution-freeze.json'), results=[])
    try:
        for row in commands:
            start = time.monotonic()
            with Path(row['output']).open('xb') as out, Path(row['log']).open('xb') as log:
                proc = subprocess.Popen(row['command'], stdout=out, stderr=log, env=os.environ | {'OMP_NUM_THREADS':'1'})
                peak = 0
                try:
                    while proc.poll() is None:
                        stat = Path(f'/proc/{proc.pid}/status')
                        if stat.exists():
                            values = stat.read_text().splitlines()
                            rss = [int(s.split()[1])*1024 for s in values if s.startswith('VmRSS:')]
                            peak = max([peak]+rss)
                        if peak > 2*1024**3 or shutil.disk_usage(OUT).free < 8*1024**3 or time.monotonic()-started > 1800:
                            raise RuntimeError('alignment resource or wall deadline exceeded')
                        time.sleep(.2)
                    if proc.returncode:
                        raise RuntimeError(f'aligner exit {proc.returncode}')
                except BaseException:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    raise
            result = row | dict(exit_code=proc.returncode, seconds=time.monotonic()-start, observed_process_peak_rss_bytes=peak, output_sha256=sha(Path(row['output'])), log_sha256=sha(Path(row['log'])))
            receipt['results'].append(result)
            (target/'progress.json').write_text(json.dumps(receipt,indent=2)+'\n')
            print(json.dumps(result),flush=True)
        receipt['complete'] = True
    except BaseException as exc:
        receipt['error'] = repr(exc)
        raise
    finally:
        receipt.update(seconds=time.monotonic()-started, outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in target.glob('*') if p.is_file() and p.name not in ['progress.json','receipt.json']})
        (target/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__':
    main()
