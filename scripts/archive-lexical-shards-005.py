#!/usr/bin/env python3
"""Preserve the superseded 005 shards and both verified historical aliases."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess

spec = importlib.util.spec_from_file_location('archive', Path(__file__).with_name('archive-verified-authoring.py'))
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def main():
    assert os.geteuid() == 0 and os.path.ismount(archive.MOUNT)
    assert subprocess.check_output(['hostname'], text=True).strip() == 'ozzz-aosp'
    root = archive.ROOT / 'artifacts'
    catalog = json.loads((root / 'lexical-shards-005/catalog.json').read_text())
    fixture = json.loads((root / 'lexical-qualification-006/manifest.json').read_text())
    assert catalog['schema'] == 'vipi-lexical-shards-1' and len(catalog['shards']) == 11
    assert {r['language']: r['sha256'] for r in catalog['shards']} == {r['language']: r['sha256'] for r in fixture['shards']}
    output = root / 'archive-lexical-shards-005'
    output.mkdir(exist_ok=False)
    receipt = dict(complete=False, owner='01a16e0d-ac69-7dd0-872a-8cf087160515', files=[],
                   catalog_sha256=archive.digest(root / 'lexical-shards-005/catalog.json'),
                   source_retained=True, original_paths_preserved=True)

    def save():
        temporary = output / 'receipt.tmp'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        temporary.replace(output / 'receipt.json')

    save()
    for row in catalog['shards']:
        language = row['language']
        assert language in {'en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko', 'sw'}
        paths = [root / directory / (language + '.sqlite')
                 for directory in ('lexical-shards-005', 'lexical-qualification-006')]
        assert all(p.is_file() and not p.is_symlink() for p in paths)
        before = paths[0].stat()
        assert before.st_nlink == 2 and paths[1].stat().st_ino == before.st_ino
        archive.idle(paths[0])
        assert before.st_size == row['bytes'] and archive.digest(paths[0]) == row['sha256']
        relative = 'vipi/20261027-lexical-shards-005/' + language + '.sqlite'
        destination = archive.MOUNT / relative
        assert not destination.exists()
        remote = 'dev-workspaces/' + relative
        subprocess.run(archive.SSH + [archive.REMOTE, 'mkdir -p ' + shlex.quote(str(Path(remote).parent))], check=True)
        subprocess.run(['rsync', '-a', '--no-owner', '--no-group', '--protect-args', '-e', shlex.join(archive.SSH),
                        str(paths[0]), archive.REMOTE + ':' + remote], check=True)
        assert destination.stat().st_size == row['bytes'] and archive.remote_digest(destination) == row['sha256']
        record = dict(language=language, bytes=row['bytes'], sha256=row['sha256'], destination=str(destination), aliases=[])
        receipt['files'].append(record)
        save()
        for path in paths:
            archive.idle(path)
            stat = path.stat()
            assert (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            temporary = path.with_name(path.name + '.verified-remote')
            assert not temporary.exists() and not temporary.is_symlink()
            temporary.symlink_to(destination)
            temporary.replace(path)
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            record['aliases'].append(str(path))
            save()
    receipt['complete'] = True
    receipt['archived_bytes'] = sum(r['bytes'] for r in receipt['files'])
    save()
    print(json.dumps(dict(complete=True, archived_bytes=receipt['archived_bytes'])), flush=True)


if __name__ == '__main__':
    main()
