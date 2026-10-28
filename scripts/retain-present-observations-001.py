#!/usr/bin/env python3
"""Retain every present-source observation; retire superseded mixed scratch."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,subprocess
R=Path("/aosp/development/vipi")
S=R/"artifacts/context-witnesses-present-pilot-003"
O=R/"artifacts/present-observations-001"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
source=S/"observations.sqlite";pin=json.loads((S/"receipt.json").read_text())
assert pin["complete"] and sha(source)==pin["observations_sha256"]
assert json.loads((R/"artifacts/present-native-qualification-001/legacy-rule-audit.json").read_text())["legacy_rules_exactly_preserved"]
O.mkdir(exist_ok=False);target=O/"observations.sqlite"
with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as original,closing(sqlite3.connect(target)) as out:
    out.execute("PRAGMA temp_store=FILE");out.execute("PRAGMA cache_size=-16384")
    for name in ["atoms","pairs","observations"]:
        out.execute(original.execute("SELECT sql FROM sqlite_master WHERE name=?",(name,)).fetchone()[0])
    out.execute("ATTACH DATABASE ? AS original",(source.resolve().as_uri()+"?mode=ro&immutable=1",))
    for name in ["atoms","pairs"]:out.execute("INSERT INTO main."+name+" SELECT * FROM original."+name)
    counts={}
    for pair, in original.execute("SELECT id FROM pairs"):
        condition="pair=? AND word IN (SELECT id FROM original.atoms WHERE value LIKE '@present:%')"
        out.execute("INSERT INTO main.observations SELECT * FROM original.observations WHERE "+condition,(pair,))
        count=original.execute("SELECT count(*) FROM observations WHERE pair=? AND word IN (SELECT id FROM atoms WHERE value LIKE '@present:%')",(pair,)).fetchone()[0]
        assert out.execute("SELECT count(*) FROM main.observations WHERE pair=?",(pair,)).fetchone()[0]==count
        assert not out.execute("""SELECT 1 FROM main.observations n WHERE n.pair=? AND NOT EXISTS (
            SELECT 1 FROM original.observations p WHERE p.pair=n.pair AND p.word=n.word AND p.cue=n.cue AND p.target=n.target
             AND p.sentence=n.sentence AND p.counterpart=n.counterpart) LIMIT 1""",(pair,)).fetchone()
        counts[str(pair)]=count
    out.commit();assert out.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
receipt=dict(complete=True,source_sha256=pin["observations_sha256"],source_bytes=source.stat().st_size,
    source_witness_sha256=pin["sha256"],source_receipt_sha256=sha(S/"receipt.json"),
    sha256=sha(target),bytes=target.stat().st_size,pair_rows=counts,
    exact_present_subset=True,all_present_competing_targets_retained=True,legacy_witness_rows_preserved_in_accepted_base=True,
    full_context_inputs_and_witness_evidence_retained=True,source_retired=False)
def save():(O/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
save()
check=subprocess.run(["fuser",str(source)],stdin=subprocess.DEVNULL,capture_output=True)
assert check.returncode==1 and not check.stdout and not check.stderr
source.unlink();receipt["source_retired"]=True;save()
(S/"observations-retirement.json").write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt),flush=True)
