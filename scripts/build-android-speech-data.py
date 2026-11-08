#!/usr/bin/env python3
"""Build pinned offline English/Swahili data from retained eSpeak sources on disk."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cmake', required=True, type=Path)
    parser.add_argument('--ninja', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--verify-against', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / 'android/vendor/espeak-ng'
    args.build_dir.mkdir(parents=True, exist_ok=True)
    assert not str(args.build_dir.resolve()).startswith(('/dev/shm/', '/run/'))
    subprocess.run([str(args.cmake), '-S', str(root / 'android/app/src/main/cpp'), '-B', str(args.build_dir),
                    '-G', 'Ninja', '-DCMAKE_MAKE_PROGRAM=' + str(args.ninja), '-DCMAKE_BUILD_TYPE=Release'], check=True)
    subprocess.run([str(args.cmake), '--build', str(args.build_dir), '--parallel', '2'], check=True)
    if not args.verify_against:
        assert not args.output.exists(), 'Refuse to overwrite retained generated speech data'
    with tempfile.TemporaryDirectory(prefix='speech-data-', dir=args.build_dir) as temporary:
        staging = Path(temporary)
        data = staging / 'bundle/espeak-ng-data'
        shutil.copytree(source / 'espeak-ng-data', data)
        dictionary = staging / 'dictsource'
        shutil.copytree(source / 'dictsource', dictionary)
        extra = dictionary / 'extra'
        if extra.is_dir():
            for item in extra.iterdir():
                if item.is_file():
                    destination = dictionary / item.name
                    assert not destination.exists()
                    shutil.copy2(item, destination)
        subprocess.run([str(args.build_dir / 'vipi-speech-data'), str(data.parent),
                        str(source / 'phsource'), str(dictionary) + '/', 'en', 'sw'], check=True)
        rows = [{'path': str(path.relative_to(data.parent)), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                for path in sorted(data.rglob('*')) if path.is_file()]
        manifest = {'schema': 'vipi-native-speech-data-1',
                    'espeak_revision': '699e79690f23e2558d990a3a78b0050745b96932',
                    'dictionary_languages': ['en', 'sw'], 'phoneme_sample_rate': 22050,
                    'production_use': 'English/Swahili fallback; working installed offline voices preferred', 'files': rows}
        if args.verify_against:
            previous = json.loads((args.verify_against / 'manifest.json').read_text())
            assert rows == previous['files'], 'Regenerated data differs from the retained assets'
            print('Verified identical regenerated speech data:', len(rows), 'files')
        else:
            shutil.copytree(data.parent, args.output)
            (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            print('Generated speech data:', len(rows), 'files,', sum(row['bytes'] for row in rows), 'bytes')

if __name__ == '__main__':
    main()
