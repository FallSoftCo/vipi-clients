#!/usr/bin/env python3
"""Import directly aligned PGV segments with duplicate-component exclusions.

The TMX archives lack article IDs. Components protect linked/duplicate segments;
they do not establish document-independent evaluation or semantic correctness.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from build_corpus_exclusions import fingerprint
from conversation_corpus import sha_file,write_json
from fetch_parallel_global_voices import LANGUAGES

RECIPE="vipi-pgv-components-1:85-development:15-reserved"
XML_LANG="{http://www.w3.org/XML/1998/namespace}lang"


class Components:
    def __init__(self):self.parents={}
    def root(self,value):
        parents=self.parents;parents.setdefault(value,value)
        while parents[value]!=value:
            parents[value]=parents[parents[value]];value=parents[value]
        return value
    def join(self,a,b):
        a,b=self.root(a),self.root(b)
        if a!=b:self.parents[max(a,b)]=min(a,b)


def segments(path):
    with zipfile.ZipFile(path) as archive:
        names=[n for n in archive.namelist() if n.endswith(".tmx")]
        assert len(names)==1
        with archive.open(names[0]) as stream:
            body=None
            for event,element in ET.iterparse(stream,events=["start","end"]):
                if event=="start" and element.tag=="body":body=element
                if event!="end" or element.tag!="tu":continue
                variants=[]
                for variant in element.findall("tuv"):
                    code=variant.attrib[XML_LANG]
                    seg=variant.find("seg");assert seg is not None
                    text=unicodedata.normalize("NFC"," ".join("".join(seg.itertext()).split()))
                    variants.append((LANGUAGES[code],text))
                scores=[p.text for p in element.findall("prop") if p.attrib.get("type")=="score"]
                assert len(scores)==1
                yield element.attrib["tuid"],float(scores[0]),variants
                assert body is not None
                body.clear()


def build(args):
    args.output.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    acquired=json.loads((args.source/"receipt.json").read_text())
    exclusions=json.loads((args.exclusions.parent/"receipt.json").read_text())
    assert acquired["schema"]=="vipi-pgv-acquisition-1" and acquired["complete"]
    assert exclusions["schema"]=="vipi-existing-corpus-exclusions-1" and exclusions["complete"]
    assert sha_file(args.exclusions)==exclusions["sha256"]
    archives=[v for v in acquired["archives"] if not args.language or
              args.language in [LANGUAGES[x] for x in v["pair"].split("-")]]
    assert archives
    source_hashes=sqlite3.connect(args.exclusions.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    path=args.output/"corpus.sqlite";db=sqlite3.connect(path)
    db.executescript("""PRAGMA temp_store=FILE;PRAGMA cache_size=-32768;
        CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT NOT NULL,text TEXT NOT NULL,owner TEXT NOT NULL,
            normalized_sha256 BLOB UNIQUE NOT NULL,component INTEGER,partition TEXT);
        CREATE TABLE links(a INTEGER NOT NULL,b INTEGER NOT NULL,PRIMARY KEY(a,b)) WITHOUT ROWID;
        CREATE TABLE link_evidence(a INTEGER NOT NULL,b INTEGER NOT NULL,archive TEXT NOT NULL,unit TEXT NOT NULL,score REAL NOT NULL,
            PRIMARY KEY(archive,unit)) WITHOUT ROWID;
        CREATE TABLE attribution(sentence INTEGER NOT NULL,archive TEXT NOT NULL,unit TEXT NOT NULL,
            PRIMARY KEY(sentence,archive,unit)) WITHOUT ROWID;
        CREATE TABLE tags(sentence INTEGER,tag INTEGER,owner TEXT,added TEXT);
        CREATE TABLE tag_metadata(id INTEGER PRIMARY KEY,name TEXT);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;""")
    components=Components();known={};blocked=set();inspected=set();counts=Counter();pair_counts=Counter()

    def node(language,text,archive,unit):
        digest=fingerprint(language,text)
        identifier=-(int.from_bytes(digest[:8],"big") & ((1<<62)-1))-1
        if identifier in known:
            assert known[identifier]==digest,"Truncated identity collision"
            counts["duplicate_normalized_segments"]+=1
        else:
            known[identifier]=digest;components.root(identifier)
            owner="Global Voices contributors; PGV "+archive+"#tu="+unit
            db.execute("INSERT INTO sentences VALUES (?,?,?,?,?,NULL,NULL)",(identifier,language,text,owner,digest))
            if source_hashes.execute("SELECT 1 FROM hashes WHERE digest=?",(digest,)).fetchone():blocked.add(identifier)
        db.execute("INSERT OR IGNORE INTO attribution VALUES (?,?,?)",(identifier,archive,unit))
        return identifier

    for archive in archives:
        file=args.source/(archive["pair"]+".zip")
        assert file.stat().st_size==archive["bytes"] and sha_file(file)==archive["sha256"]
        expected={LANGUAGES[x] for x in archive["pair"].split("-")}
        for unit,score,variants in segments(file):
            counts["source_alignments"]+=1
            if len(variants)!=2 or {r[0] for r in variants}!=expected:
                counts["invalid_language_geometry"]+=1;continue
            if not math.isfinite(score) or score<=0 or any(not text or len(text)>100_000 for _,text in variants):
                counts["empty_nonpositive_or_oversized"]+=1;continue
            a,b=[node(language,text,archive["url"],unit) for language,text in variants]
            components.join(a,b);a,b=sorted((a,b))
            db.execute("INSERT OR IGNORE INTO links VALUES (?,?)",(a,b))
            db.execute("INSERT INTO link_evidence VALUES (?,?,?,?,?)",(a,b,archive["url"],unit,score))
            pair_counts[archive["pair"]]+=1
            # Three early public examples were inspected during format discovery.
            # They cannot later be described as unseen evaluation material.
            if archive["pair"]=="eng-swa" and unit in {"1","2","3"}:inspected.update((a,b))
            if counts["source_alignments"]%5000==0:db.commit()
        db.commit();print(json.dumps(dict(pair=archive["pair"],retained_alignments=pair_counts[archive["pair"]])),flush=True)
    excluded_roots={components.root(v) for v in blocked}
    inspected_roots={components.root(v) for v in inspected}
    partition_counts=Counter();batch=[]
    for identifier in sorted(known):
        root=components.root(identifier)
        value=hashlib.sha256((RECIPE+":"+str(root)).encode()).digest()
        split="reserved" if int.from_bytes(value[:8],"big")%100<15 else "development"
        if root in inspected_roots:split="development"
        if root in excluded_roots:split="excluded-existing-source"
        partition_counts[split]+=1;batch.append((root,split,identifier))
        if len(batch)>=5000:
            db.executemany("UPDATE sentences SET component=?,partition=? WHERE id=?",batch);db.commit();batch=[]
    db.executemany("UPDATE sentences SET component=?,partition=? WHERE id=?",batch)
    db.execute("CREATE INDEX partition_lookup ON sentences(partition,language,id)");db.commit()
    by_language={}
    for language,split,count in db.execute("SELECT language,partition,count(*) FROM sentences GROUP BY language,partition"):
        by_language[language+":"+split]=count
    receipt=dict(schema="vipi-pgv-corpus-1",complete=True,source_receipt_sha256=sha_file(args.source/"receipt.json"),
        archives=[dict(pair=v["pair"],url=v["url"],sha256=v["sha256"]) for v in archives],
        exclusions_sha256=exclusions["sha256"],compiler_sha256=sha_file(Path(__file__)),recipe=RECIPE,
        counts=dict(counts),pairs=dict(pair_counts),partitions=dict(partition_counts),languages=by_language,
        sentences=len(known),direct_links=db.execute("SELECT count(*) FROM links").fetchone()[0],
        direct_links_only=True,excluded_matching_sentences=len(blocked),excluded_components=len(excluded_roots),
        inspected_components=len(inspected_roots),license="CC-BY-4.0: PGV alignment distribution; Global Voices attribution license retained",
        citation=acquired["citation"],automatic_alignment=True,independent_semantic_acceptance=False,release_ready=False,
        duplicate_policy="Case/whitespace-equivalent segments share one identity; original variants remain in pinned archives, attributed by archive URL and tuid.",
        evaluation_limit="Direct-link/duplicate components only. TMX has no article identifiers; no document-independent evaluation claim.")
    db.execute("INSERT INTO metadata VALUES ('receipt',?)",(json.dumps(receipt,sort_keys=True),));db.commit()
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    db.close();source_hashes.close()
    receipt.update(bytes=path.stat().st_size,sha256=sha_file(path),seconds=round(time.monotonic()-started,3))
    write_json(args.output/"receipt.json",receipt)
    (args.output/"ATTRIBUTION.txt").write_text(acquired["citation"]+"\n"+
        "Source: https://nlp.ilsp.gr/pgv/ . PGV alignments: CC BY 4.0. Original text: Global Voices contributors, attribution license.\n"+
        "Original archives and README notices are retained. Archive URL and translation-unit ID are retained in attribution and link_evidence.\n"+
        "Changes: NFC/whitespace normalization, duplicate collapse, direct-link indexing, source exclusion and component partitioning.\n"+
        "Automatically aligned candidate material; not independently accepted language mappings.\n")
    print(json.dumps({k:receipt[k] for k in ["sentences","direct_links","partitions","bytes","sha256","seconds"]}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["source","exclusions","output"]:parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--language",choices=sorted(LANGUAGES.values()))
    build(parser.parse_args())
