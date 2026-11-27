#!/usr/bin/env python3
"""Build pinned offline voice data from retained eSpeak sources on disk."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Dictionary identifiers for the local translation catalog. Mandarin uses cmn.
# Norwegian Bokmål selects voice nb at runtime and reads no_dict.
DICTIONARIES = (
    "af ar be bg bn ca cmn cs cy da de el en eo es et fa fi fr ga gu he hi hr ht hu "
    "id is it ja ka kn ko lt lv mk mr ms mt nl no pl pt ro ru sk sl sq sv sw ta te "
    "th tr uk ur vi"
).split()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Explicit verified source checkout for an inactive build",
    )
    parser.add_argument("--cmake", required=True, type=Path)
    parser.add_argument("--ninja", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-against", type=Path)
    parser.add_argument("--languages", nargs="+", default=DICTIONARIES)
    args = parser.parse_args()
    assert len(set(args.languages)) == len(args.languages)
    assert set(args.languages) <= set(DICTIONARIES)
    root = (
        args.source_root.resolve()
        if args.source_root
        else Path(__file__).resolve().parents[1]
    )
    if args.source_root:
        pinned = {
            "android/vendor/espeak-ng": "67fb2c58e516542ebab3b3238e2a48d163de6482",
            "android/vendor/sonic": "204be21e5303198d293c0e76f317d747f9ef54e8",
            "android/app/src/main/cpp/CMakeLists.txt": "d85aeb72122f2f086ac1cb9ef48595b5f848db12",
            "android/app/src/main/cpp/config.h": "7ba4830e9c4e35bb96446e1c6e357f92c8b74117",
            "android/app/src/main/cpp/speech_data.c": "d07a148ff91f7da2c1a7d2bd3786b5586055dcce",
        }
        for path, tree in pinned.items():
            actual = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD:" + path], text=True
            ).strip()
            assert actual == tree, "Unrecognized pinned speech source tree: " + path
        status = subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                *pinned,
            ],
            text=True,
        )
        assert not status.strip(), "Modified or untracked speech sources require review"
    source = root / "android/vendor/espeak-ng"
    args.build_dir.mkdir(parents=True, exist_ok=True)
    assert not str(args.build_dir.resolve()).startswith(("/dev/shm/", "/run/"))
    subprocess.run(
        [
            str(args.cmake),
            "-S",
            str(root / "android/app/src/main/cpp"),
            "-B",
            str(args.build_dir),
            "-G",
            "Ninja",
            "-DCMAKE_MAKE_PROGRAM=" + str(args.ninja),
            "-DCMAKE_BUILD_TYPE=Release",
        ],
        check=True,
    )
    subprocess.run(
        [str(args.cmake), "--build", str(args.build_dir), "--parallel", "2"], check=True
    )
    if not args.verify_against:
        assert not args.output.exists(), (
            "Refuse to overwrite retained generated speech data"
        )
    with tempfile.TemporaryDirectory(
        prefix="speech-data-", dir=args.build_dir
    ) as temporary:
        staging = Path(temporary)
        data = staging / "bundle/espeak-ng-data"
        shutil.copytree(source / "espeak-ng-data", data)
        dictionary = staging / "dictsource"
        shutil.copytree(source / "dictsource", dictionary)
        extra = dictionary / "extra"
        if extra.is_dir():
            for item in extra.iterdir():
                if item.is_file():
                    destination = dictionary / item.name
                    assert not destination.exists()
                    shutil.copy2(item, destination)
        subprocess.run(
            [
                str(args.build_dir / "vipi-speech-data"),
                str(data.parent),
                str(source / "phsource"),
                str(dictionary) + "/",
                *args.languages,
            ],
            check=True,
        )
        rows = [
            {
                "path": str(path.relative_to(data.parent)),
                "bytes": path.stat().st_size,
                "sha256": sha(path),
            }
            for path in sorted(data.rglob("*"))
            if path.is_file()
        ]
        voices = {}
        for dictionary_id in args.languages:
            code = "zh" if dictionary_id == "cmn" else dictionary_id
            voice = "nb" if dictionary_id == "no" else dictionary_id
            if not (data / (dictionary_id + "_dict")).is_file():
                raise ValueError("Missing compiled dictionary: " + dictionary_id)
            voices[code] = {"voice": voice, "dictionary": dictionary_id}
        manifest = {
            "schema": "vipi-native-speech-data-1",
            "espeak_revision": "699e79690f23e2558d990a3a78b0050745b96932",
            "dictionary_languages": args.languages,
            "voices": voices,
            "phoneme_sample_rate": 22050,
            "production_use": "Bundled fallback; working installed offline voices preferred. Japanese engine requires Kana input.",
            "files": rows,
        }
        if args.verify_against:
            previous = json.loads((args.verify_against / "manifest.json").read_text())
            assert manifest == previous, (
                "Regenerated data or manifest differs from the retained assets"
            )
            print("Verified identical regenerated speech data:", len(rows), "files")
        else:
            shutil.copytree(data.parent, args.output)
            (args.output / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
            print(
                "Generated speech data:",
                len(rows),
                "files,",
                sum(row["bytes"] for row in rows),
                "bytes",
            )


if __name__ == "__main__":
    main()
