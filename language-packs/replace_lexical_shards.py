#!/usr/bin/env python3
"""Assemble a full dictionary release with explicitly replaced language shards.

Each source is verified before copying. Only release metadata changes in the
copies; the original revisions remain immutable. Changed languages need fresh
context mining, including negative observations.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from build_wiktextract import canonical, digest_file

POLICY = "native-linked-language-replacement-1"

def read_catalog(path):
    catalog = json.loads(path.read_text())
    assert catalog["schema"] == "vipi-lexical-shards-1"
    assert len(catalog["shards"]) == len({r["language"] for r in catalog["shards"]})
    return catalog

def build(args):
    baseline = read_catalog(args.base)
    originals = {r["language"]: (args.base, baseline, r) for r in baseline["shards"]}
    selected = dict(originals)
    changed = set()
    for path in args.replacement:
        replacement = read_catalog(path)
        assert replacement["inventory_sha256"] == baseline["inventory_sha256"]
        for row in replacement["shards"]:
            language = row["language"]
            assert language in originals and language not in changed
            selected[language] = (path, replacement, row)
            changed.add(language)
    assert changed and changed < set(originals), "A bounded language replacement is required"
    recipe = dict(policy=POLICY, compiler_sha256=digest_file(Path(__file__)),
        baseline_catalog_sha256=digest_file(args.base),
        replacement_catalogs=[dict(path=str(p), sha256=digest_file(p)) for p in args.replacement],
        changed_languages=sorted(changed))
    release = hashlib.sha256(canonical(recipe).encode()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    provenance = []
    for language in sorted(selected):
        catalog_path, catalog, row = selected[language]
        source = catalog_path.parent / (language + ".sqlite")
        assert source.stat().st_size == row["bytes"] and digest_file(source) == row["sha256"]
        destination = args.output / source.name
        shutil.copyfile(source, destination)
        assert digest_file(destination) == row["sha256"], "Copy differs from pinned source"
        with closing(sqlite3.connect(destination)) as db:
            db.execute("PRAGMA temp_store=FILE")
            db.execute("PRAGMA cache_size=-8192")
            metadata = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM metadata")}
            assert metadata["language"] == language
            assert metadata["source_inventory_sha256"] == baseline["inventory_sha256"]
            assert metadata["release_id"] == catalog["release_id"]
            # Keep each shard's compiler policy, sense records and eligibility.
            # The shared identity lets native readers reject mixed installations.
            for key, value in dict(release_id=release,
                source_shard_release_id=catalog["release_id"],
                source_shard_sha256=row["sha256"], language_replacement_delta=recipe).items():
                db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, canonical(value)))
            db.commit()
            assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        result = dict(row, sha256=digest_file(destination), bytes=destination.stat().st_size,
            language_recompiled=language in changed, source_catalog_sha256=digest_file(catalog_path),
            source_shard_sha256=row["sha256"], source_shard_release_id=catalog["release_id"],
            source_compiler_policy=metadata["policy"])
        records.append(result)
        provenance.append(dict(language=language, replaced=language in changed,
            source=str(source), source_sha256=row["sha256"], output_sha256=result["sha256"],
            lexical_records_unchanged_from_selected_source=True))
        print(canonical(dict(language=language, replaced=language in changed,
            bytes=result["bytes"])), flush=True)
    catalog = dict(schema=baseline["schema"], policy=POLICY, release_id=release,
        inventory_sha256=baseline["inventory_sha256"], compiler_sha256=recipe["compiler_sha256"],
        base_release_id=baseline["release_id"], changed_languages=sorted(changed),
        shards=records, total_bytes=sum(r["bytes"] for r in records), delta_identity=recipe,
        runtime_qualified=False, release_ready=False,
        mutation_scope="Replace the declared languages; all other lexical records are copied unchanged. Every shard receives the same release identity. Fresh affected-pair contexts are required.",
        limits=baseline.get("limits", []))
    (args.output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    receipt = dict(complete=True, recipe=recipe, release_id=release,
        catalog_sha256=digest_file(args.output / "catalog.json"), shards=provenance,
        independent_semantic_acceptance=False, native_qualified=False)
    (args.output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    with (args.output / "ATTRIBUTION.txt").open("x") as out:
        for path in [args.base, *args.replacement]:
            out.write((path.parent / "ATTRIBUTION.txt").read_text() + "\n")
        out.write("Assembly: exact source shards with shared release metadata; original compiler and source hashes retained per language.\n")
    print(canonical(dict(complete=True, release_id=release, changed_languages=sorted(changed))))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=lambda v: Path(v).resolve(), required=True)
    parser.add_argument("--replacement", type=lambda v: Path(v).resolve(), action="append", required=True)
    parser.add_argument("--output", type=lambda v: Path(v).resolve(), required=True)
    build(parser.parse_args())
