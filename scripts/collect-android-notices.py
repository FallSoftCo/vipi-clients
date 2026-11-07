#!/usr/bin/env python3
"""Package actual notices from the resolved release artifacts; no network access.

Run the pinned Gradle wrapper with -I ../scripts/android-dependency-inventory.gradle
:app:vipiDependencyInventory, then invoke this script. Missing embedded notices
remain visible in the index; this is provenance, not a licensing opinion.
"""
import argparse
import hashlib
import io
import json
import pathlib
import zipfile


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', type=pathlib.Path, default=root/'android/app/build/reports/vipi/runtime-dependencies.json')
    parser.add_argument('--output', type=pathlib.Path, default=root/'android/app/src/main/assets/legal/third-party')
    args = parser.parse_args()
    rows = json.loads(args.inventory.read_text())
    texts = args.output/'texts'; texts.mkdir(parents=True, exist_ok=True)
    packages = []; used = set()
    for row in rows:
        if row['coordinate'].startswith('Vipi:'):
            continue
        artifact = pathlib.Path(row['path'])
        package = {k: row.get(k) for k in ['coordinate', 'classifier', 'type']}
        with artifact.open('rb') as source:
            package['artifact_sha256'] = hashlib.file_digest(source, 'sha256').hexdigest()
        package['notices'] = []
        def capture(source, prefix=''):
            for name in sorted(source.namelist()):
                leaf = pathlib.PurePosixPath(name).name.lower()
                if name.endswith('/') or not any(word in leaf for word in ['license', 'notice', 'copyright']):
                    continue
                if pathlib.PurePosixPath(name).suffix.lower() not in ['', '.txt', '.md', '.html', '.json']:
                    continue
                data = source.read(name)
                if not data:
                    continue
                data.decode('utf-8', errors='strict')
                digest = hashlib.sha256(data).hexdigest(); filename = digest + '.txt'
                target = texts/filename
                if target.exists():
                    assert target.read_bytes() == data
                else:
                    target.write_bytes(data)
                used.add(filename)
                package['notices'].append({'original_path': prefix+name, 'asset': 'legal/third-party/texts/'+filename, 'sha256': digest, 'bytes': len(data)})
        with zipfile.ZipFile(artifact) as source:
            capture(source)
            if artifact.suffix == '.aar':
                for name in sorted(source.namelist()):
                    if name == 'classes.jar' or (name.startswith('libs/') and name.endswith('.jar')):
                        assert source.getinfo(name).file_size <= 64 * 1024 * 1024
                        with zipfile.ZipFile(io.BytesIO(source.read(name))) as nested:
                            capture(nested, name+'!/')
        packages.append(package)
    # Only this generator's content-addressed files are candidates for retirement.
    for path in texts.glob('*.txt'):
        if path.name not in used:
            path.unlink()
    index = {'schema': 1, 'configuration': 'releaseRuntimeClasspath', 'packages': packages,
             'notice': 'These are verbatim notices supplied by the resolved dependency artifacts. Additional pinned upstream licenses are listed separately. A missing embedded notice does not imply a license grant.'}
    (args.output/'index.json').write_text(json.dumps(index, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'packages': len(packages), 'notice_files': len(used), 'notice_bytes': sum(p.stat().st_size for p in texts.glob('*.txt'))}))


if __name__ == '__main__':
    main()
