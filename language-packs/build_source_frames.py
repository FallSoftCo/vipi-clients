#!/usr/bin/env python3
"""Compile specifically reviewed finite source contexts, preserving provenance.

This compiler writes a candidate directory. Installing it in an app is a separate
step after native route qualification; seed evidence never grants new senses.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def variants(parts):
    states = [("", None)]
    for part in parts:
        assert len(part) == 1
        kind, value = next(iter(part.items()))
        assert kind in ("literal", "slot", "focus")
        choices = value if kind == "slot" else [value]
        assert 1 <= len(choices) <= 32
        states = [(prefix + suffix,
                   (len(prefix.encode("utf-16-le")) // 2,
                    len((prefix + suffix).encode("utf-16-le")) // 2)
                   if kind == "focus" else focus)
                  for prefix, focus in states for suffix in choices]
        assert len(states) <= 1024
    assert all(focus is not None for _, focus in states)
    return [{"context": text, "focus_utf16": list(focus)}
            for text, focus in sorted(set(states))]


def compile_pair(language, permission):
    inputs = permission["pairs"][language]
    seed = ROOT / "data/immersion" / f"en-{language}.sqlite"
    starter = ROOT / "data/immersion" / inputs["starter_file"]
    assert digest(seed.read_bytes()) == inputs["seed_sha256"]
    assert digest(starter.read_bytes()) == inputs["starter_sha256"]
    entries = json.loads(starter.read_bytes())["entries"]
    groups = collections.defaultdict(list)
    with sqlite3.connect(seed.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("pragma query_only=on")
        for identifier, payload, evidence in db.execute(
                "select id,payload,evidence from mappings order by id"):
            row, witness = json.loads(payload), json.loads(evidence)
            assert identifier == row["id"]
            if len(row["source_parts"]) == 1:
                continue
            assert sum("focus" in part for part in row["source_parts"]) == 1
            groups[encoded(row["source_parts"]).decode()].append((row, witness))
    approved = set(inputs["pattern_ids"])
    assert len(approved) == len(inputs["pattern_ids"])
    patterns = []
    for key, records in sorted(groups.items()):
        identifier = "frame-" + digest(("en-" + language + "\0" + key).encode())[:24]
        if identifier not in approved:
            continue
        assert len({(row["source"], row["target"], row["reading"], row["meaning"])
                    for row, _ in records}) == 1
        row = records[0][0]
        original_face = row["target"]
        correction = inputs["target_corrections"].get(identifier)
        if correction:
            assert original_face == correction["before"]
        target = correction["after"] if correction else original_face
        concepts = {entry["concept_id"] for entry in entries
                    if entry["source"] == row["source"] and entry["target"] == original_face}
        assert len(concepts) <= 1
        # Case-only corrections retain the previously reviewed semantic ID.
        concept = next(iter(concepts)) if concepts else "frame-concept-" + digest(
            ("en-" + language + "\0" + row["meaning"] + "\0" + row["source"] +
             "\0" + original_face).encode())[:24]
        references = [{"id": record["id"], "record_sha256": record["record_sha256"],
                       "proof_sha256": digest(encoded({"payload": record, "evidence": witness}))}
                      for record, witness in records]
        pattern = dict(id=identifier, pair="en-" + language, source=row["source"],
                       target=target, reading=row["reading"], meaning=row["meaning"],
                       concept_id=concept, source_only_permission=True,
                       source_parts=row["source_parts"], variants=variants(row["source_parts"]),
                       original_records=references)
        if correction:
            pattern["display_correction"] = correction
        patterns.append(pattern)
    assert {row["id"] for row in patterns} == approved
    assert set(inputs["target_corrections"]) <= approved
    version = f"source-frames-en-{language}-001"
    return dict(schema="vipi-source-frame-pack-1", version=version, source="en",
                target=language, policy=permission["policy"],
                approval_sha256=digest(encoded(permission)), patterns=patterns)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), "Use a new candidate directory; retained artifacts are immutable."
    permission_path = Path(__file__).with_name("source-frame-approval-001.json")
    permission = json.loads(permission_path.read_bytes())
    assert permission["schema"] == "vipi-source-frame-approval-1"
    assert permission["source_only_permission"] is True
    candidates = [compile_pair(language, permission) for language in ("ja", "sw")]
    args.output.mkdir(parents=True)
    receipt = {"compiler_sha256": digest(Path(__file__).read_bytes()),
               "approval_file_sha256": digest(permission_path.read_bytes()),
               "runtime_installed": False, "outputs": {}}
    for pack in candidates:
        filename = pack["version"] + ".json"
        content = encoded(pack) + b"\n"
        manifest = dict(schema="vipi-source-frame-manifest-1", file=filename,
                        sha256=digest(content), bytes=len(content), version=pack["version"],
                        source=pack["source"], target=pack["target"], patterns=len(pack["patterns"]),
                        policy=pack["policy"])
        catalog_name = f"source-frames-en-{pack['target']}-catalog.json"
        for name, data in ((filename, content), (catalog_name, encoded(manifest) + b"\n")):
            (args.output / name).write_bytes(data)
            receipt["outputs"][name] = dict(bytes=len(data), sha256=digest(data))
    (args.output / "build-receipt.json").write_bytes(encoded(receipt) + b"\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
