#!/usr/bin/env python3
"""Build bundle008 in the Mac login session and compare actual iPad translations."""
from pathlib import Path
import hashlib,json,subprocess,os,time
ROOT=Path("/Users/Apple/Development/vipi")
DEVICE="7B6D180F-1D57-5036-8E42-C057698FBAB2"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def main():
    os.chdir(ROOT)
    release=json.loads((ROOT/".runtime/bundled-lexical-transfer-008/release-receipt.json").read_text())
    assert release["complete"] and sha(ROOT/"data/lexical/catalog.json")==release["bundle_sha256"]
    simulator=json.loads((ROOT/"artifacts/bundled-conversations-simulator-011.json").read_text())
    assert simulator["complete"] and not simulator["failures"] and simulator["bundled_catalog_sha256"]==release["bundle_sha256"]
    stage=ROOT/"artifacts/ipad-bundled-lexical-008";stage.mkdir(exist_ok=False)
    started=time.time()
    command=["xcodebuild","-workspace","Vipi.xcworkspace","-scheme","Vipi","-configuration","Debug",
        "-destination","platform=iOS,id="+DEVICE,"-derivedDataPath","../build/ios-device",
        "-allowProvisioningUpdates","build-for-testing"]
    with (stage/"build.log").open("x") as f:
        build=subprocess.run(command,cwd=ROOT/"ios",stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
    assert build.returncode==0,"Inspect exact signing/build error before another attempt"
    cases=[("artifacts/ipad-past-capture-002/cases.json","451"),
        ("artifacts/past-verb-grammar-regressions-001/cases.json","460")]
    for path,run in cases:
        subprocess.run(["python3","scripts/replay-bundled-conversations-ipad.py","--cases",path,
            "--run",run,"--expected-catalog",release["bundle_sha256"]],stdin=subprocess.DEVNULL,check=True)
    receipt=dict(complete=True,physical=True,bundle_sha256=release["bundle_sha256"],elapsed_seconds=time.time()-started,
        runs=[dict(run=run,cases_sha256=sha(ROOT/path),
            report_sha256=sha(ROOT/("artifacts/bundled-conversations-ipad-"+run+".json"))) for path,run in cases],
        acoustic_listening_accepted=False,semantic_accuracy_claim=False,store_ready=False)
    (stage/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt),flush=True)
if __name__=="__main__":main()
