#!/usr/bin/env python3
"""Bounded isolated Apertium stage capture; no app or system installation."""
import hashlib
import json
import os
from pathlib import Path
import resource
import shlex
import shutil
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = Path(sys.argv[1]).resolve()
    protocol = json.loads((out / 'protocol.json').read_text())
    assert json.loads((out / 'acquisition.json').read_text())['complete']
    limits = protocol['resources']
    assert shutil.disk_usage(out).free > limits['minimum_free_bytes'] + limits['max_added_bytes']
    resource.setrlimit(resource.RLIMIT_AS, (limits['max_probe_rss_bytes'], limits['max_probe_rss_bytes']))
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    os.sched_setaffinity(0, {max(os.sched_getaffinity(0))})
    root = out / 'root'
    mode = root / 'usr/share/apertium/modes/eng-spa.mode'
    commands = [[str(root / 'usr/bin/apertium-destxt')]]
    for part in mode.read_text().strip().split('|'):
        argv = shlex.split(part)
        argv[0] = str(root / 'usr/bin' / argv[0])
        argv = ['-g' if x == '$1' else str(root) + x if x.startswith('/usr/share/') else x
                for x in argv if x != '$2']
        commands.append(argv)
    commands.append([str(root / 'usr/bin/apertium-retxt')])
    assert all(Path(c[0]).is_file() for c in commands)
    freeze = dict(production=False, protocol_sha256=digest(out / 'protocol.json'),
                  runner_sha256=digest(Path(__file__)), mode_sha256=digest(mode), commands=commands,
                  bindings='Canonical mode $1=-g (retain unknown markers), $2 empty; only private path relocation. Standard txt deformatter/reformatter. No translation API or target correction.',
                  inference_network_calls=0, corpus_experiment_changed=False)
    path = out / 'execution-freeze.json'
    with path.open('x') as handle:
        json.dump(freeze, handle, indent=2); handle.write('\n')
    environment = os.environ.copy()
    environment['LD_LIBRARY_PATH'] = str(root / 'usr/lib/x86_64-linux-gnu')
    environment['LC_ALL'] = 'C.UTF-8'
    started = time.monotonic()
    rows = []
    complete = False
    error = None
    try:
        with (out / 'rows.jsonl').open('x') as target:
            for case in protocol['cases']:
                case_started = time.monotonic()
                value = (case['text'] + '\n').encode()
                row = dict(case, stages=[])
                for index, argv in enumerate(commands):
                    if time.monotonic() - started > limits['max_wall_seconds']:
                        raise TimeoutError('probe deadline')
                    tick = time.monotonic()
                    result = subprocess.run(argv, input=value, capture_output=True, env=environment, timeout=10)
                    stage = dict(index=index, command=Path(argv[0]).name,
                                 returncode=result.returncode, seconds=time.monotonic()-tick,
                                 output=result.stdout.decode('utf-8'), stderr=result.stderr.decode('utf-8'))
                    row['stages'].append(stage)
                    if result.returncode:
                        row['failure_stage'] = index
                        break
                    value = result.stdout
                row['complete'] = len(row['stages']) == len(commands) and all(s['returncode'] == 0 for s in row['stages'])
                row['translation'] = value.decode('utf-8').strip() if row['complete'] else None
                row['seconds'] = time.monotonic()-case_started
                rows.append(row)
                target.write(json.dumps(row, ensure_ascii=False) + '\n'); target.flush()
                assert sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) <= limits['max_added_bytes']
                assert shutil.disk_usage(out).free >= limits['minimum_free_bytes']
        complete = all(r['complete'] for r in rows)
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        receipt = dict(complete=complete, error=error, cases=len(rows), production=False,
                       seconds=time.monotonic()-started,
                       maximum_child_process_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024,
                       parent_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                       retained_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),
                       execution_freeze_sha256=digest(path), rows_sha256=digest(out / 'rows.jsonl'),
                       limits='Per-case times include every process startup and all stage capture; desktop experiment, not native mobile latency or semantic acceptance.')
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
