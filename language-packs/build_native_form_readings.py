#!/usr/bin/env python3
"""Recover supplied per-form pronunciation and ruby data omitted by the inventory.

A separate evidence database preserves original form positions and ambiguity.
This does not approve forms, infer readings, or change any running app pack.
"""
import argparse
from collections import Counter
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import time

from build_wiktextract import MAX_LINE, canonical, clean, digest_file, form_ok
from context_hints import lookup_key

LANGUAGES = {"ar", "ja", "ko", "zh"}
SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE entries(source_line INTEGER PRIMARY KEY,language TEXT NOT NULL,headword TEXT NOT NULL,
 pos TEXT NOT NULL,source_url TEXT NOT NULL);
CREATE TABLE form_readings(source_line INTEGER NOT NULL REFERENCES entries(source_line),
 form_index INTEGER NOT NULL,form TEXT NOT NULL,normalized TEXT NOT NULL,
 reading TEXT NOT NULL,ruby TEXT NOT NULL,tags TEXT NOT NULL,form_source TEXT NOT NULL,
 PRIMARY KEY(source_line,form_index)) WITHOUT ROWID;
CREATE INDEX form_lookup ON form_readings(normalized,source_line);
"""

def supplied_rows(entry):
    for index, form in enumerate(entry.get("forms", [])):
        if not isinstance(form, dict):
            continue
        written = clean(form.get("form", ""))
        reading = clean(form.get("roman", "")) if isinstance(form.get("roman", ""), str) else ""
        ruby = form.get("ruby", [])
        if not isinstance(ruby, list) or any(not isinstance(x, list) or len(x) != 2
            or any(not isinstance(v, str) for v in x) for x in ruby):
            raise ValueError("Unexpected upstream ruby format")
        if not form_ok(written) or not (reading or ruby):
            continue
        tags = sorted({x for x in form.get("tags", []) if isinstance(x, str)})
        origin = form.get("source", "")
        if not isinstance(origin, str):
            raise ValueError("Unexpected upstream form source")
        yield index, written, reading, ruby, tags, origin

def build(args):
    started = time.monotonic()
    pin = json.loads(Path(__file__).with_name("sources").joinpath("wiktextract-20261021.json").read_text())
    inventory_receipt = json.loads(args.inventory.with_name("receipt.json").read_text())
    assert inventory_receipt["upstream_sha256"] == pin["source_sha256"]
    assert args.source.stat().st_size == pin["source_bytes"] and digest_file(args.source) == pin["source_sha256"]
    assert args.inventory.stat().st_size == inventory_receipt["bytes"] and digest_file(args.inventory) == inventory_receipt["sha256"]
    args.output.mkdir(parents=True, exist_ok=False)
    path = args.output / "form-readings.sqlite"
    counts = Counter()
    with closing(sqlite3.connect(args.inventory.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as inventory:
        # A line identity includes the language, headword and POS; no joins by
        # spelling can merge homographs or unrelated native entries.
        expected = {i:(language, head, pos, url) for i,language,head,pos,url in inventory.execute(
            "SELECT source_line,language,headword,part_of_speech,source_url FROM native_entries WHERE language IN ('ar','ja','ko','zh')")}
    seen = set()
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA cache_size=-16384")
        db.executescript(SCHEMA)
        with gzip.open(args.source, "rb") as stream:
            line = 0
            while raw := stream.readline(MAX_LINE+1):
                if len(raw) > MAX_LINE:
                    raise ValueError("Oversized upstream entry")
                line += 1
                if line not in expected:
                    continue
                entry = json.loads(raw)
                language = "zh" if entry.get("lang_code") == "cmn" else entry.get("lang_code")
                wanted_language, head, pos, url = expected[line]
                assert (language, clean(entry.get("word", "")), entry.get("pos")) == (wanted_language, head, pos)
                seen.add(line)
                records = list(supplied_rows(entry))
                if records:
                    db.execute("INSERT INTO entries VALUES (?,?,?,?,?)", (line, language, head, pos, url))
                    counts[language + ":entries"] += 1
                    for index,written,reading,ruby,tags,origin in records:
                        db.execute("INSERT INTO form_readings VALUES (?,?,?,?,?,?,?,?)",
                            (line,index,written,lookup_key(written,language),reading,canonical(ruby),canonical(tags),origin))
                        counts[language + ":forms"] += 1
                        counts[language + ":roman"] += bool(reading)
                        counts[language + ":ruby"] += bool(ruby)
                if len(seen) % 10000 == 0:
                    db.commit()
                    used = sum(p.stat().st_size for p in args.output.iterdir() if p.is_file())
                    if used > args.max_bytes:
                        raise ValueError("Declared evidence output budget exceeded")
                    print(canonical(dict(lines=line,matched_entries=len(seen),counts=counts)), flush=True)
        assert seen == expected.keys(), "Incomplete original source scan"
        metadata = dict(schema="vipi-native-form-readings-1",
            upstream_sha256=pin["source_sha256"],inventory_sha256=inventory_receipt["sha256"],
            compiler_sha256=digest_file(Path(__file__)),languages=sorted(LANGUAGES),
            interpretation="Supplied upstream readings and ruby only; no inference, sense approval or runtime promotion.",
            license=pin["license"],source_line_identity="full-upstream-file")
        db.executemany("INSERT INTO metadata VALUES (?,?)", [(k,canonical(v)) for k,v in metadata.items()])
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None
    assert path.stat().st_size <= args.max_bytes
    receipt = dict(**metadata,complete=True,source_entries=line,matched_inventory_entries=len(seen),
        counts=counts,bytes=path.stat().st_size,sha256=digest_file(path),
        seconds=round(time.monotonic()-started,2),native_qualified=False,semantic_accuracy_claim=False,
        source_hash_rechecked=True,inventory_hash_rechecked=True)
    (args.output / "receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    (args.output / "ATTRIBUTION.txt").write_text(
        "Wiktionary contributors; extraction by Tatu Ylonen/wiktextract via Kaikki.org.\n"
        "CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/\n"
        "Exact original source: " + pin["source_url"] + "; SHA-256 " + pin["source_sha256"] + "\n"
        "Changes: indexed supplied per-form romanization/ruby, features and original form positions.\n"
        "Original entry URLs and source-line identities are retained; no generated readings.\n")
    print(canonical(receipt),flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source","inventory","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--max-bytes",type=int,default=512*1024**2)
    build(parser.parse_args())
