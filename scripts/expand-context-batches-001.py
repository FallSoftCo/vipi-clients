#!/usr/bin/env python3
"""One bounded, immutable continuation of the PGV context expansion.

Build the remaining 88 non-Swahili/non-English-French directions, then replace
complete pair scopes. Two independent compiler processes share the existing
storage admission guard. There is no automatic retry of an uncertain build.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path("/aosp/development/vipi")
OWNER = "01a16e0d-ac69-7dd0-872a-8cf087160515"
PYTHON = str(ROOT / ".venv-lexical-context/bin/python")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_source():
    snapshot = json.loads(
        (ROOT / "artifacts/cumulative-witness-source-001/receipt.json").read_text()
    )
    for row in snapshot["files"]:
        assert sha(ROOT / "language-packs" / row["file"]) == row["sha256"]


def checked_revision(name):
    directory = ROOT / "artifacts" / name
    receipt = json.loads((directory / "receipt.json").read_text())
    assert (
        receipt["complete"] and sha(directory / "witnesses.sqlite") == receipt["sha256"]
    )
    return receipt


def archive_observations(name):
    subprocess.run(
        [
            "python3",
            "scripts/archive-verified-authoring.py",
            "--artifact",
            name + "/observations.sqlite",
            "--digest-key",
            "observations_sha256",
            "--revision",
            "20261027-" + name,
            "--owner",
            OWNER,
        ],
        check=True,
    )


def compile_batch(row):
    checked_source()
    output = ROOT / "artifacts" / row["revision"]
    assert not output.exists()
    command = [
        "runuser",
        "-u",
        "aosp",
        "--",
        "/usr/local/bin/storage-build",
        "--peak-bytes",
        str(row["peak_bytes"]),
        "--",
        PYTHON,
        "language-packs/build_context_witnesses.py",
        "--contexts",
        "artifacts/lexical-contexts-001/contexts.sqlite",
        "--additional-context",
        "artifacts/lexical-contexts-pgv-001/contexts.sqlite",
        "--additional-corpus-receipt",
        "artifacts/parallel-global-voices-001/receipt.json",
        "--source-exclusions",
        "artifacts/corpus-exclusions-001/hashes.sqlite",
        "--release-adapter",
        "artifacts/context-witnesses-003/witnesses.sqlite",
        "--base-supplement-receipt",
        "artifacts/swahili-corpus-001/receipt.json",
        "--output",
        str(output),
    ]
    for pair in row["pairs"]:
        command += ["--pair", pair]
    with Path(str(output) + ".log").open("x") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    receipt = checked_revision(row["revision"])
    assert set(receipt["requested_pairs"]) == set(row["pairs"])
    archive_observations(row["revision"])
    print(
        json.dumps(
            dict(
                stage="compiled",
                revision=row["revision"],
                rules=receipt["counts"]["witnesses"],
                bytes=receipt["bytes"],
            )
        ),
        flush=True,
    )
    return row["revision"]


def main():
    assert (
        os.geteuid() == 0
        and subprocess.check_output(["hostname"], text=True).strip() == "ozzz-aosp"
    )
    os.chdir(ROOT)
    checked_source()
    # The already started English-French build must be complete before invoking
    # this continuation. Its exact result is verified, never restarted.
    first = checked_revision("context-witnesses-cumulative-enfr-001")
    assert set(first["requested_pairs"]) == {"en-fr", "fr-en"}
    old = json.loads(Path("artifacts/lexical-contexts-001/receipt.json").read_text())
    new = json.loads(
        Path("artifacts/lexical-contexts-pgv-001/receipt.json").read_text()
    )
    counts = {
        k: old["pairs"].get(k, 0) + v
        for k, v in new["pairs"].items()
        if "sw" not in k.split("-") and k != "en-fr"
    }
    groups = [["en-es"]]
    current, total = [], 0
    for pair, count in sorted(counts.items(), key=lambda r: r[1], reverse=True):
        if pair == "en-es":
            continue
        if current and total + count > 2400000:
            groups.append(current)
            current, total = [], 0
        current.append(pair)
        total += count
    if current:
        groups.append(current)
    # Smaller script-diverse pairs go first. English-Spanish uses its own
    # allowance; all estimates include observations, witnesses and journals.
    groups.reverse()
    rows = []
    for number, group in enumerate(groups, 1):
        pairs = sorted(
            [
                direction
                for pair in group
                for direction in (pair, "-".join(reversed(pair.split("-"))))
            ]
        )
        rows.append(
            dict(
                revision=f"context-witnesses-cumulative-batch-{number:03d}",
                pairs=pairs,
                candidate_alignments=sum(counts[k] for k in group),
                peak_bytes=(6 if group == ["en-es"] else 4) * 1024**3,
            )
        )
    plan = dict(
        schema="vipi-cumulative-expansion-plan-1",
        owner=OWNER,
        batches=rows,
        compiler_snapshot_sha256=sha(
            Path("artifacts/cumulative-witness-source-001/receipt.json")
        ),
        driver_sha256=sha(Path(__file__)),
        completed_prior=["sw", "en-fr"],
        basis="Swahili build: 163401728-byte observations plus 18812928-byte witnesses; English-French measured 400072704-byte observations at 800000 reference spans; allowances include growth and journals.",
    )
    output = Path("artifacts/cumulative-expansion-001")
    output.mkdir(exist_ok=False)
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    archive_observations("context-witnesses-cumulative-enfr-001")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(compile_batch, row) for row in rows]
        for future in as_completed(futures):
            future.result()
    parent = "context-witnesses-004"
    revisions = ["context-witnesses-cumulative-enfr-001"] + [
        row["revision"] for row in rows
    ]
    for number, replacement in enumerate(revisions, 5):
        checked_source()
        target = f"context-witnesses-{number:03d}"
        assert not Path("artifacts", target).exists()
        with Path("artifacts", target + ".log").open("x") as log:
            subprocess.run(
                [
                    "runuser",
                    "-u",
                    "aosp",
                    "--",
                    "/usr/local/bin/storage-build",
                    "--peak-bytes",
                    str(2 * 1024**3),
                    "--",
                    PYTHON,
                    "language-packs/replace_context_witness_pairs.py",
                    "--base",
                    f"artifacts/{parent}/witnesses.sqlite",
                    "--replacement",
                    f"artifacts/{replacement}/witnesses.sqlite",
                    "--output",
                    f"artifacts/{target}",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        receipt = checked_revision(target)
        print(
            json.dumps(
                dict(
                    stage="replaced",
                    revision=target,
                    rules=receipt["counts"]["witnesses"],
                    bytes=receipt["bytes"],
                )
            ),
            flush=True,
        )
        parent = target
    receipt = checked_revision(parent)
    all_pairs = {pair for pair in receipt["pair_input_revisions"]}
    assert len(all_pairs) == 110
    (output / "receipt.json").write_text(
        json.dumps(
            dict(
                complete=True,
                final_revision=parent,
                sha256=receipt["sha256"],
                bytes=receipt["bytes"],
                rules=receipt["counts"]["witnesses"],
                recomputed_directions=110,
                native_qualified=False,
                semantic_acceptance=False,
                plan_sha256=sha(output / "plan.json"),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
