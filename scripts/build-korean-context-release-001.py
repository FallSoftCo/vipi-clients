#!/usr/bin/env python3
"""Recompute Korean contexts after exact negative homograph link corrections."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path("/aosp/development/vipi")
OUTPUT = ROOT / "artifacts/korean-context-release-001"
SNAPSHOT = OUTPUT / "compiler-source"
PYTHON = ROOT / ".venv-lexical-context/bin/python"
LANGUAGES = ["ar", "de", "en", "es", "fr", "it", "ja", "ko", "pt", "sw", "zh"]
SOURCES = {
    "tatoeba": dict(
        corpus="conversation-corpus-002",
        output="lexical-contexts-korean-review-001",
        base="lexical-contexts-past-review-002",
        peak=2 * 1024**3,
    ),
    "pgv": dict(
        corpus="parallel-global-voices-001",
        output="lexical-contexts-pgv-korean-review-001",
        base="lexical-contexts-pgv-past-review-002",
        peak=2 * 1024**3,
    ),
    "massive": dict(
        corpus="massive-corpus-003",
        output="lexical-contexts-massive-korean-review-001",
        base="lexical-contexts-massive-past-review-002",
        peak=1024**3,
    ),
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def verify():
    for row in json.loads((SNAPSHOT / "receipt.json").read_text())["files"]:
        assert sha(SNAPSHOT / row["file"]) == row["sha256"], row["file"]


def stage_context(name):
    verify()
    row = SOURCES[name]
    source = ROOT / "artifacts" / row["corpus"] / "corpus.sqlite"
    pin = json.loads((source.parent / "receipt.json").read_text())
    working = ROOT / "artifacts/swahili-context-release-002" / ("working-" + name)
    corpus = working / "corpus.sqlite"
    retained = json.loads((working / "working-copy-receipt.json").read_text())
    assert retained["verified"] and not retained["retired_after_build"]
    assert (
        corpus.stat().st_size == pin["bytes"]
        and sha(corpus) == pin["sha256"] == retained["sha256"]
    )
    assert sha(working / "receipt.json") == sha(source.parent / "receipt.json")
    scratch = OUTPUT / ("scratch-" + name)
    scratch.mkdir()
    command = [
        str(PYTHON),
        str(SNAPSHOT / "qa/immersion/build_lexical_contexts.py"),
        "--shards",
        str(ROOT / "artifacts/lexical-shards-020"),
        "--corpus",
        str(corpus),
        "--output",
        str(ROOT / "artifacts" / row["output"]),
        "--pair-language",
        "ko",
    ]
    if name == "tatoeba":
        command += [
            "--supplement",
            str(ROOT / "artifacts/swahili-corpus-001/corpus.sqlite"),
        ]
    subprocess.run(
        command,
        cwd=ROOT,
        env=dict(os.environ, TMPDIR=str(scratch)),
        stdin=subprocess.DEVNULL,
        check=True,
    )
    receipt = json.loads(
        (ROOT / "artifacts" / row["output"] / "receipt.json").read_text()
    )
    assert receipt["complete"] and not receipt["pilot"]
    assert receipt["changed_pair_languages"] == ["ko"]
    assert receipt["corpus_sha256"] == pin["sha256"]
    shutil.rmtree(scratch)
    print(
        json.dumps(
            dict(stage="contexts_complete", source=name, bytes=receipt["bytes"])
        ),
        flush=True,
    )


def guarded(name, peak, command):
    verify()
    with (ROOT / "artifacts" / (name + ".log")).open("x") as log:
        subprocess.run(
            [
                "storage-build",
                "--peak-bytes",
                str(peak),
                "--",
                str(PYTHON),
                *map(str, command),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            check=True,
        )


def main():
    os.chdir(ROOT)
    review = ROOT / "artifacts/lexical-korean-links-001/receipt.json"
    accepted = json.loads(review.read_text())
    assert accepted["accepted_for_context_mining"]
    assert accepted["catalog_sha256"] == sha(
        ROOT / "artifacts/lexical-korean-links-001/catalog.json"
    )
    assembled = json.loads(
        (ROOT / "artifacts/lexical-shards-020/receipt.json").read_text()
    )
    catalog = ROOT / "artifacts/lexical-shards-020/catalog.json"
    assert assembled["complete"] and assembled["catalog_sha256"] == sha(catalog)
    OUTPUT.mkdir(exist_ok=False)
    SNAPSHOT.mkdir()
    files = []
    for folder in ["language-packs", "qa/immersion"]:
        for source in sorted((ROOT / folder).glob("*.py")):
            relative = source.relative_to(ROOT)
            destination = SNAPSHOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files.append(dict(file=str(relative), sha256=sha(destination)))
    shutil.copy2(Path(__file__), SNAPSHOT / "driver.py")
    files.append(dict(file="driver.py", sha256=sha(SNAPSHOT / "driver.py")))
    write(SNAPSHOT / "receipt.json", dict(files=files))
    write(
        OUTPUT / "plan.json",
        dict(
            owner="01a16e0d-ac69-7dd0-872a-8cf087160515",
            dictionary_catalog_sha256=sha(catalog),
            source_review_sha256=sha(review),
            compiler_snapshot_sha256=sha(SNAPSHOT / "receipt.json"),
            sources=SOURCES,
            changed_languages=["ko"],
            expected_recomputed_directions=20,
            expected_total_directions=110,
            admission_basis="Reuse exact verified disk copies of the same 1.76 GB, 2.14 GB and 0.22 GB source corpora. No new source copies. Reuse the measured Arabic changed-language 2/2/1 GiB context budgets. The past batch001 included every Korean pair plus other languages and used 1.16 GB observations for 1.03M references; Korean alone has substantially fewer references. Bound witness scratch to 1 GiB and preserve admission.",
            automatic_retries=False,
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(
                guarded,
                row["output"],
                row["peak"],
                [SNAPSHOT / "driver.py", "--context-stage", name],
            )
            for name, row in SOURCES.items()
        ]
        for job in as_completed(jobs):
            job.result()
    pairs = sorted(
        a + "-" + b for a in LANGUAGES for b in LANGUAGES if a != b and "ko" in [a, b]
    )
    command = [
        SNAPSHOT / "language-packs/build_context_witnesses.py",
        "--contexts",
        ROOT / "artifacts" / SOURCES["tatoeba"]["output"] / "contexts.sqlite",
        "--additional-context",
        ROOT / "artifacts" / SOURCES["pgv"]["output"] / "contexts.sqlite",
        "--additional-corpus-receipt",
        ROOT / "artifacts/parallel-global-voices-001/receipt.json",
        "--extra-context",
        ROOT / "artifacts" / SOURCES["massive"]["output"] / "contexts.sqlite",
        "--extra-corpus-receipt",
        ROOT / "artifacts/massive-corpus-003/receipt.json",
        "--source-exclusions",
        ROOT / "artifacts/corpus-exclusions-001/hashes.sqlite",
        "--base-supplement-receipt",
        ROOT / "artifacts/swahili-corpus-001/receipt.json",
        "--output",
        ROOT / "artifacts/context-witnesses-korean-review-001",
    ]
    for pair in pairs:
        command += ["--pair", pair]
    guarded("context-witnesses-korean-review-001", 1024**3, command)
    command = [
        SNAPSHOT / "language-packs/replace_context_witness_pairs.py",
        "--base",
        ROOT / "artifacts/context-witnesses-019/witnesses.sqlite",
        "--replacement",
        ROOT / "artifacts/context-witnesses-korean-review-001/witnesses.sqlite",
        "--output",
        ROOT / "artifacts/context-witnesses-020",
        "--dictionary-baseline",
        ROOT / "artifacts/lexical-shards-019/catalog.json",
        "--dictionary-catalog",
        catalog,
    ]
    for row in SOURCES.values():
        command += [
            "--base-context-receipt",
            ROOT / "artifacts" / row["base"] / "receipt.json",
            "--replacement-context-receipt",
            ROOT / "artifacts" / row["output"] / "receipt.json",
        ]
    command += [
        "--base-pair-receipt",
        ROOT / "artifacts/context-witnesses-past-review-002/receipt.json",
    ]
    guarded("context-witnesses-020", 2 * 1024**3, command)
    guarded(
        "context-pair-packs-020",
        512 * 1024**2,
        [
            SNAPSHOT / "language-packs/export_context_pair_packs.py",
            "--source",
            ROOT / "artifacts/context-witnesses-020/witnesses.sqlite",
            "--catalog",
            catalog,
            "--output",
            ROOT / "artifacts/context-pair-packs-020",
        ],
    )
    guarded(
        "bundled-lexical-009",
        768 * 1024**2,
        [
            SNAPSHOT / "language-packs/bundle_lexical_data.py",
            "--base",
            catalog,
            "--catalog",
            catalog,
            "--contexts",
            ROOT / "artifacts/context-pair-packs-020/catalog.json",
            "--output",
            ROOT / "artifacts/bundled-lexical-009",
        ],
    )
    bundle = ROOT / "artifacts/bundled-lexical-009/catalog.json"
    meta = json.loads(bundle.read_text())
    assert meta["directed_pairs"] == 110
    proof = ROOT / "artifacts/context-witnesses-020/recomputation-proof.json"
    write(
        OUTPUT / "receipt.json",
        dict(
            complete=True,
            bundle_sha256=sha(bundle),
            dictionary_catalog_sha256=sha(catalog),
            recomputation_proof_sha256=sha(proof),
            changed_directions=20,
            total_directions=110,
            compressed_bytes=meta["compressed_bytes"],
            native_qualified=False,
            semantic_accuracy_claim=False,
        ),
    )
    print(
        "Complete Korean link-correction bundle; native qualification required.",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-stage", choices=sorted(SOURCES))
    args = parser.parse_args()
    if args.context_stage:
        stage_context(args.context_stage)
    else:
        main()
