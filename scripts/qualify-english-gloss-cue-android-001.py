#!/usr/bin/env python3
"""Stage one exact experimental witness; restore the prior QA witness finally."""
from pathlib import Path
import hashlib,json,runpy,subprocess,time
ROOT=Path("/aosp/development/vipi")
h=runpy.run_path(str(ROOT/"scripts/qualify-context-case-android-001.py"))
run=h["run"];adb=h["adb"];sha=h["sha"];staged_out=h["staged_out"]
pin=json.loads((ROOT/"artifacts/english-gloss-cue-candidate-001/receipt.json").read_text())
for row in pin["files"]:assert sha(ROOT/row["path"])==row["candidate_sha256"]
log=ROOT/"artifacts/english-gloss-cue-android-build-001.log"
build_deadline=time.monotonic()+1800
while '"exit_code": 0' not in log.read_text():
    assert time.monotonic()<build_deadline,"Native build did not complete"
    assert '"exit_code": 1' not in log.read_text(),"Native build failed"
    time.sleep(5)
assert "BUILD SUCCESSFUL" in log.read_text()
with staged_out("english-gloss-install-001"):
    run("python3","scripts/install-lexical-candidate-android.py","--run","022")
baseline=ROOT/"artifacts/lexical-coverage-android-519.json"
deadline=time.monotonic()+3600
witness=ROOT/"artifacts/context-witnesses-518/witnesses.sqlite"
receipt=witness.with_name("receipt.json")
while not receipt.exists() or not baseline.exists():
    assert time.monotonic()<deadline,"Qualification prerequisites did not finish"
    time.sleep(10)
assert json.loads(baseline.read_text())["passed"]
meta=json.loads(receipt.read_text());assert meta["complete"] and sha(witness)==meta["sha256"]
device="files/context-witnesses-518.sqlite"
state=dict(complete=False,candidate_removed=False,sha256=meta["sha256"],bytes=meta["bytes"],
    purpose="Temporary exact public QA witness; accounts, keys, messages and translation models preserved.")
report=ROOT/"artifacts/english-gloss-cue-android-staging-001.json";assert not report.exists()
def save():report.write_text(json.dumps(state,indent=2)+chr(10))
save()
with staged_out("english-gloss-candidate-001"):
    try:
        with witness.open("rb") as stream:
            subprocess.run(h["ADB"]+["shell","run-as co.fallsoft.vipi sh -c 'cat > "+device+"'"],
                stdin=stream,capture_output=True,check=True)
        assert adb("shell","run-as","co.fallsoft.vipi","sha256sum",device).split()[0]==meta["sha256"]
        run("python3","scripts/run-lexical-candidate-android.py","--run","520","--fixture","514","--witness","518")
        run("python3","scripts/run-lexical-candidate-android.py","--run","613","--fixture","600","--witness","518")
        state["complete"]=True
    finally:
        adb("shell","am","force-stop","co.fallsoft.vipi")
        adb("shell","run-as","co.fallsoft.vipi","rm",device)
        state["candidate_removed"]=True;save()
with staged_out("english-gloss-broad-001"):
    run("python3","scripts/replay-bundled-conversations-android.py","--run","019",
        "--cases","artifacts/bundled-development-004/combined-cases.json",
        "--expected-catalog","6b8040ae0eacb82dded24d9cf948649551195165d3d1c12a085e17e02e847300")
print("English glossary cue qualification complete; exact staging restored.",flush=True)
