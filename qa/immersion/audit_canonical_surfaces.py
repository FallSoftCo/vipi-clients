#!/usr/bin/env python3
"""Read-only audit of canonical spellings, separating mapped and guard lexemes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zlib


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--reuse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained audit")
    args.output.mkdir(parents=True)
    catalog_path = args.assets / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    report = {"schema": "vipi-canonical-surface-audit-1", "catalog_sha256": sha(catalog_path),
              "runner_sha256": sha(Path(__file__)), "production_changes": False, "languages": []}
    for entry in catalog["files"]:
        if not entry["id"].startswith("d-"):
            continue
        language = entry["id"][2:]
        retained = args.reuse / (entry["id"] + ".sqlite")
        path = retained if retained.exists() else args.output / "current-shard.sqlite"
        temporary = path != retained
        if temporary:
            if path.exists():
                raise RuntimeError("uncertain temporary shard already exists")
            if shutil.disk_usage(args.output).free < entry["bytes"] + 8 * 1024**3:
                raise RuntimeError("insufficient bounded disk reserve")
            source = args.assets / entry["file"]
            assert sha(source) == entry["compressed_sha256"]
            decoder = zlib.decompressobj()
            with source.open("rb") as compressed, path.open("xb") as expanded:
                while chunk := compressed.read(1024**2):
                    expanded.write(decoder.decompress(chunk))
                expanded.write(decoder.flush())
            assert decoder.eof
        assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"]
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute("""SELECT l.*,
            EXISTS(SELECT 1 FROM terms t WHERE t.lexeme=l.id AND t.eligible=1) AS eligible_links
            FROM lexemes l WHERE l.target_safe=1 AND NOT EXISTS
            (SELECT 1 FROM surfaces s WHERE s.normalized=l.normalized AND s.lexeme=l.id AND s.surface=l.headword)
            ORDER BY l.id"""
        )]
        linked = [row for row in rows if row["eligible_links"]]
        competitors = [row for row in rows if not row["eligible_links"]]
        inspect = linked + competitors[:12]
        ids = {row["id"] for row in inspect}
        forms = collections.defaultdict(list)
        if ids:
            # One bounded scan, not a full-table lookup per missing headword.
            for row in db.execute("SELECT * FROM surfaces WHERE lexeme IN (" + ",".join("?" for _ in ids) + ")", tuple(ids)):
                forms[row["lexeme"]].append(dict(row))
        for row in inspect:
            row["retained_forms"] = forms[row["id"]]
        item = {"language": language, "dictionary_sha256": entry["sha256"],
                "target_safe_lexemes": db.execute("SELECT count(*) FROM lexemes WHERE target_safe=1").fetchone()[0],
                "eligible_linked_lexemes": db.execute("SELECT count(*) FROM lexemes l WHERE target_safe=1 AND EXISTS(SELECT 1 FROM terms t WHERE t.lexeme=l.id AND eligible=1)").fetchone()[0],
                "canonical_absent_linked": len(linked), "canonical_absent_competition_only": len(competitors),
                "linked_missing": linked, "competition_only_examples": competitors[:12]}
        db.close()
        report["languages"].append(item)
        (args.output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({key: value for key, value in item.items() if key not in ("linked_missing", "competition_only_examples")}), flush=True)
        if temporary:
            path.unlink()
    report["complete"] = True
    report["limits"] = ["Literal headword presence only. No invented citation stems, new sense links, readings, or morphology.",
                        "Competition-only entries preserve negative ambiguity evidence; they are not promised translation vocabulary."]
    (args.output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
