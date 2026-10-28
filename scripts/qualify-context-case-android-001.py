#!/usr/bin/env python3
"""Qualify the pinned native case revision; exact temporary QA staging only."""
import contextlib,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path("/aosp/development/vipi")
ADB=["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb","-s","emulator-5620"]
def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def adb(*args):return subprocess.check_output(ADB+list(args),stdin=subprocess.DEVNULL).decode().strip()
def run(*args):subprocess.run(list(args),cwd=ROOT,stdin=subprocess.DEVNULL,check=True)
@contextlib.contextmanager
def staged_out(label):
    local=ROOT/"artifacts/context-witnesses-506/witnesses.sqlite"
    pin=json.loads(local.with_name("receipt.json").read_text())
    device="files/context-witnesses-506.sqlite"
    assert pin["complete"] and sha(local)==pin["sha256"]
    assert adb("shell","run-as","co.fallsoft.vipi","sha256sum",device).split()[0]==pin["sha256"]
    path=ROOT/("artifacts/context-case-android-staging-"+label+".json")
    assert not path.exists()
    state=dict(complete=False,restored=False,local=str(local),device=device,sha256=pin["sha256"],purpose="Temporary exact QA staging release; no model/key/account/message reset.")
    def save():path.write_text(json.dumps(state,indent=2)+chr(10))
    save()
    adb("shell","am","force-stop","co.fallsoft.vipi")
    adb("shell","run-as","co.fallsoft.vipi","rm",device)
    try:
        yield
        state["complete"]=True
    finally:
        with local.open("rb") as stream:
            subprocess.run(ADB+["shell","run-as co.fallsoft.vipi sh -c 'cat > "+device+"'"],stdin=stream,capture_output=True,check=True)
        assert adb("shell","run-as","co.fallsoft.vipi","sha256sum",device).split()[0]==pin["sha256"]
        state["restored"]=True;save()
def main():
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        result=subprocess.run(ADB+["shell","getprop","sys.boot_completed"],stdin=subprocess.DEVNULL,capture_output=True,text=True)
        if result.returncode==0 and result.stdout.strip()=="1":break
        time.sleep(2)
    else:raise RuntimeError("Owned emulator did not finish booting")
    assert adb("emu","avd","name").splitlines()[0]=="vipi-api35-20261024"
    pin=json.loads((ROOT/"artifacts/context-case-source-002/receipt.json").read_text())
    for row in pin["files"]:assert sha(ROOT/row["path"])==row["sha256"]
    log=(ROOT/"artifacts/context-case-android-build-002.log").read_text()
    assert "BUILD SUCCESSFUL" in log and '"exit_code": 0' in log
    with staged_out("install-001"):
        run("python3","scripts/install-lexical-candidate-android.py","--run","016")
    run("python3","scripts/run-lexical-candidate-android.py","--run","515","--fixture","511","--witness","506")
    run("python3","scripts/run-lexical-candidate-android.py","--run","610","--fixture","600","--witness","506")
    with staged_out("broad-001"):
        run("python3","scripts/replay-bundled-conversations-android.py","--run","017","--cases","artifacts/bundled-development-004/combined-cases.json",
            "--expected-catalog","6b8040ae0eacb82dded24d9cf948649551195165d3d1c12a085e17e02e847300")
    path=ROOT/"artifacts/context-case-emulator-capacity-001.json"
    state=json.loads(path.read_text());state.update(restart_required=False,restarted_at=time.time())
    path.write_text(json.dumps(state,indent=2)+chr(10))
    print("Native case qualification completed; emulator staging restored.",flush=True)
if __name__=="__main__":main()
