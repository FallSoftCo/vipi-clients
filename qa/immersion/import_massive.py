#!/usr/bin/env python3
"""Import attributed, unlocalized MASSIVE training pairs without split leakage.

MASSIVE supplies localized assistant requests, not representative friend chats.
Only original English-to-locale relations are linked. Localized slot values are
not literal translations and are excluded; no foreign-to-foreign edges are
inferred through English. Source judgments are filters, not meaning acceptance.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import itertools
import json
from pathlib import Path
import re
import sqlite3
import tarfile
import time
import unicodedata
from build_corpus_exclusions import fingerprint
from conversation_corpus import sha_file, write_json
from import_parallel_global_voices import Components

LOCALES = {"en-US":"en", "es-ES":"es", "fr-FR":"fr", "de-DE":"de",
    "it-IT":"it", "pt-PT":"pt", "ar-SA":"ar", "zh-CN":"zh",
    "ja-JP":"ja", "ko-KR":"ko", "sw-KE":"sw"}
SLOT = re.compile(r"\[([^\[\]:]+)\s*:\s*([^\[\]]+)\]")
POLICY = "massive-original-train-direct-unlocalized-1"

def compact(text):
    return "".join(unicodedata.normalize("NFC", text).split())

def slots(row):
    annotated = row["annot_utt"]
    matches = list(SLOT.finditer(annotated))
    remainder = SLOT.sub(lambda m: m.group(2), annotated)
    if "[" in remainder or "]" in remainder or compact(remainder) != compact(row["utt"]):
        return None
    return Counter(m.group(1).strip() for m in matches)

def usable(row, english):
    own, original = slots(row), slots(english)
    if own is None or original is None or own != original:
        return "invalid_or_changed_slots"
    if row["intent"] != english["intent"] or row["scenario"] != english["scenario"]:
        return "changed_intent"
    if row["locale"] == "en-US":
        return None
    methods = row.get("slot_method", [])
    if any(m["method"] not in {"translation", "unchanged"} for m in methods):
        return "localized_or_unknown_slot_method"
    if set(own) != {m["slot"] for m in methods}:
        return "missing_slot_method"
    judgments = row.get("judgments", [])
    if len(judgments) < 2:
        return "missing_judgments"
    if any(j["intent_score"] != 1 or j["slots_score"] not in {1, 2}
           or j["grammar_score"] < 3 or j["spelling_score"] != 2
           or j["language_identification"] not in {"target", "target|english"}
           for j in judgments):
        return "source_judgment_disagreement"
    return None

def partition(component_partitions, excluded, inspected):
    if excluded:
        return "excluded-existing-source"
    if inspected:
        return "excluded-inspected"
    if component_partitions != {"train"}:
        return "reserved"
    return "development"

def build(args):
    started = time.monotonic()
    acquired = json.loads((args.source / "receipt.json").read_text())
    assert acquired["complete"] and acquired["version"] == "1.1"
    archive = args.source / "amazon-massive-dataset-1.1.tar.gz"
    entry = next(r for r in acquired["sources"] if r["file"] == archive.name)
    assert archive.stat().st_size == entry["bytes"] and sha_file(archive) == entry["sha256"]
    exclusions = json.loads((args.exclusions.parent / "receipt.json").read_text())
    prior = json.loads((args.prior_corpus.parent / "receipt.json").read_text())
    assert exclusions["complete"] and sha_file(args.exclusions) == exclusions["sha256"]
    assert prior["complete"] and sha_file(args.prior_corpus) == prior["sha256"]
    evaluation_hashes = set()
    evaluation_sources = []
    for path in args.evaluation_exclusions:
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
            evaluation_hashes.update(r[0] for r in db.execute("SELECT digest FROM hashes"))
        evaluation_sources.append(dict(file=str(path),sha256=sha_file(path),kind="hashes"))
    for path in args.evaluation_cases:
        for row in json.loads(path.read_text()):
            evaluation_hashes.add(fingerprint(row["source"],row["original"]))
            evaluation_hashes.add(fingerprint(row["target"],row["translation"]))
        evaluation_sources.append(dict(file=str(path),sha256=sha_file(path),kind="replay-cases"))
    assert evaluation_hashes
    args.output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as license_archive:
        for name in ["LICENSE","NOTICE.md","CITATION.md"]:
            with license_archive.extractfile("1.1/"+name) as stream:
                (args.output/("SOURCE-"+name)).write_bytes(stream.read())
    rows = defaultdict(dict)
    with tarfile.open(archive) as source:
        for locale in LOCALES:
            with source.extractfile("1.1/data/" + locale + ".jsonl") as stream:
                for line in stream:
                    if not line.strip(): continue
                    row = json.loads(line)
                    assert row["locale"] == locale and row["partition"] in {"train", "dev", "test"}
                    identifier = row["id"]
                    assert locale not in rows[identifier]
                    rows[identifier][locale] = row
    assert all(set(group) == set(LOCALES) for group in rows.values())
    path = args.output / "corpus.sqlite"
    counts, reasons, by_language = Counter(), Counter(), Counter()
    components = Components()
    known, raw_partitions, inspected, blocked, accepted = {}, defaultdict(set), set(), set(), set()
    with closing(sqlite3.connect(path)) as db, \
         closing(sqlite3.connect(args.exclusions.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)) as hashes, \
         closing(sqlite3.connect(args.prior_corpus.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)) as prior_db:
        db.executescript("""PRAGMA temp_store=FILE; PRAGMA cache_size=-32768;
            CREATE TABLE sentences(id INTEGER PRIMARY KEY, language TEXT NOT NULL, text TEXT NOT NULL,
                owner TEXT NOT NULL, normalized_sha256 BLOB UNIQUE NOT NULL, component INTEGER, partition TEXT);
            CREATE TABLE links(a INTEGER NOT NULL,b INTEGER NOT NULL,PRIMARY KEY(a,b)) WITHOUT ROWID;
            CREATE TABLE link_evidence(a INTEGER,b INTEGER,unit TEXT,locale TEXT,source_partition TEXT,
                PRIMARY KEY(unit,locale)) WITHOUT ROWID;
            CREATE TABLE source_rows(unit TEXT,locale TEXT,sentence INTEGER,partition TEXT,eligibility_reason TEXT,payload TEXT,
                PRIMARY KEY(unit,locale)) WITHOUT ROWID;
            CREATE TABLE tags(sentence INTEGER,tag INTEGER,owner TEXT,added TEXT);
            CREATE TABLE tag_metadata(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;""")
        # Stream archived indexes once. Per-row remote B-tree reads otherwise
        # turn a small import into hundreds of thousands of network round trips.
        prior_hashes = {r[0] for r in prior_db.execute("SELECT normalized_sha256 FROM sentences")}
        existing_hashes = {r[0] for r in hashes.execute("SELECT digest FROM hashes")}
        print(json.dumps(dict(stage="exclusions-loaded",prior_hashes=len(prior_hashes),
            existing_hashes=len(existing_hashes),evaluation_hashes=len(evaluation_hashes))),flush=True)
        for unit, group in sorted(rows.items(), key=lambda x:int(x[0])):
            assert len({r["partition"] for r in group.values()}) == 1
            ids, qualified = {}, {}
            for locale, row in group.items():
                language = LOCALES[locale]
                text = unicodedata.normalize("NFC", row["utt"])
                digest = fingerprint(language, text)
                identifier = -(1 << 62) - (int.from_bytes(digest[:8], "big") & ((1 << 60)-1))
                if identifier in known:
                    assert known[identifier] == digest, "Truncated identity collision"
                    counts["duplicate_normalized_rows"] += 1
                else:
                    known[identifier] = digest
                    components.root(identifier)
                    db.execute("INSERT INTO sentences VALUES (?,?,?,?,?,NULL,NULL)",
                        (identifier,language,text,"MASSIVE 1.1 / Amazon / SLURP; exact source rows retained",digest))
                    if digest in evaluation_hashes or digest in existing_hashes or digest in prior_hashes:
                        blocked.add(identifier)
                raw_partitions[identifier].add(row["partition"])
                if unit == "0": inspected.add(identifier)
                reason = usable(row, group["en-US"])
                reasons[reason or "eligible"] += 1
                qualified[locale] = reason is None
                ids[locale] = identifier
                db.execute("INSERT INTO source_rows VALUES (?,?,?,?,?,?)",
                    (unit,locale,identifier,row["partition"],reason,json.dumps(row,ensure_ascii=False,sort_keys=True)))
                counts["source_rows"] += 1
            # Every original parallel family participates in split/exclusion
            # propagation, including rows that cannot supply runtime evidence.
            for identifier in ids.values(): components.join(ids["en-US"],identifier)
            for locale in sorted(set(LOCALES)-{"en-US"}):
                if not (qualified["en-US"] and qualified[locale]): continue
                a,b = sorted((ids["en-US"],ids[locale]))
                db.execute("INSERT OR IGNORE INTO links VALUES (?,?)",(a,b))
                db.execute("INSERT INTO link_evidence VALUES (?,?,?,?,?)",
                    (a,b,unit,locale,group[locale]["partition"]))
                accepted.update((a,b))
            if int(unit) % 1000 == 0:
                db.commit();print(json.dumps(dict(stage="source-rows",unit=unit,rows=counts["source_rows"])),flush=True)
        partitions = defaultdict(set)
        for identifier, splits in raw_partitions.items():
            partitions[components.root(identifier)].update(splits)
        excluded_roots = {components.root(v) for v in blocked}
        inspected_roots = {components.root(v) for v in inspected}
        for identifier in known:
            root = components.root(identifier)
            split = partition(partitions[root],root in excluded_roots,root in inspected_roots)
            if split == "development" and identifier not in accepted:
                split = "excluded-unqualified"
            db.execute("UPDATE sentences SET component=?,partition=? WHERE id=?", (root,split,identifier))
        assert not any(digest in evaluation_hashes for (digest,) in
            db.execute("SELECT normalized_sha256 FROM sentences WHERE partition='development'"))
        assert not db.execute("""SELECT 1 FROM source_rows r JOIN sentences s ON s.id=r.sentence
            WHERE s.partition='development' AND r.partition<>'train' LIMIT 1""").fetchone()
        db.execute("CREATE INDEX partition_lookup ON sentences(partition,language,id)")
        db.commit()
        split_counts = dict(db.execute("SELECT partition,count(*) FROM sentences GROUP BY partition"))
        language_counts = {language+":"+split:count for language,split,count in
            db.execute("SELECT language,partition,count(*) FROM sentences GROUP BY language,partition")}
        development_links = db.execute("""SELECT count(*) FROM links l JOIN sentences a ON a.id=l.a
            JOIN sentences b ON b.id=l.b WHERE a.partition='development' AND b.partition='development'""").fetchone()[0]
        receipt = dict(schema="vipi-massive-corpus-1",complete=True,policy=POLICY,
            source_receipt_sha256=sha_file(args.source/"receipt.json"),archive_sha256=entry["sha256"],
            exclusions_sha256=exclusions["sha256"],prior_corpus_sha256=prior["sha256"],
            evaluation_exclusions=evaluation_sources,evaluation_hashes=len(evaluation_hashes),
            compiler_sha256=sha_file(Path(__file__)),
            dependencies={name:sha_file(Path(__file__).with_name(name)) for name in
                ["build_corpus_exclusions.py","conversation_corpus.py","import_parallel_global_voices.py"]},
            languages=language_counts,partitions=split_counts,counts=dict(counts),eligibility_reasons=dict(reasons),
            sentences=len(known),direct_links=db.execute("SELECT count(*) FROM links").fetchone()[0],
            development_links=development_links,excluded_components=len(excluded_roots),
            source_partition_policy="Only original train components; any dev/test duplicate family is reserved.",
            relation_policy="Only original en-US-to-locale edges with unlocalized slots and source judgments; no inferred foreign edges.",
            license="CC-BY-4.0; archive LICENSE, NOTICE, source units and contributor metadata retained.",
            independent_semantic_acceptance=False,representative_chat_coverage=False,release_ready=False)
        db.execute("INSERT INTO metadata VALUES ('receipt',?)",(json.dumps(receipt,sort_keys=True),))
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    receipt.update(bytes=path.stat().st_size,sha256=sha_file(path),seconds=round(time.monotonic()-started,3))
    write_json(args.output/"receipt.json",receipt)
    (args.output/"ATTRIBUTION.txt").write_text(
        "MASSIVE 1.1, Amazon, and original SLURP contributors. CC BY 4.0.\n"
        "https://github.com/alexa/massive ; pinned archive, LICENSE, NOTICE and contributor source rows retained.\n"
        "Changes: NFC text normalization, duplicate collapse, split/exclusion propagation, source quality and slot-method filters, direct-link indexing.\n"
        "Localized entity replacements excluded. Candidate assistant-request evidence; not accepted vocabulary mappings.\n")
    print(json.dumps({k:receipt[k] for k in ["sentences","direct_links","development_links","partitions","bytes","sha256","seconds"]}))

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["source","exclusions","prior-corpus","output"]:
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--evaluation-exclusions",type=Path,action="append",required=True)
    parser.add_argument("--evaluation-cases",type=Path,action="append",required=True)
    build(parser.parse_args())
