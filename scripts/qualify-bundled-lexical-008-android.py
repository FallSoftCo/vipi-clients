#!/usr/bin/env python3
"""Wait for the owned pack build, then run the real bundled reader on Android."""
from pathlib import Path
import hashlib,json,os,subprocess,time
ROOT=Path("/aosp/development/vipi")
os.chdir(ROOT)
ADB="/aosp/ozzz-android-toolchain/sdk/platform-tools/adb"
DEVICE="emulator-5620"
RELEASE=ROOT/"artifacts/past-verb-context-release-002/receipt.json"
REPLAY=ROOT/"artifacts/bundled-conversations-android-012.json"
CASES=ROOT/"artifacts/bundled-development-004/combined-cases.json"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def adb(*args,capture=False):
    return subprocess.run([ADB,"-s",DEVICE,*args],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,check=True)
assert RELEASE.exists(), "The completed pack receipt is required before native qualification"
release=json.loads(RELEASE.read_text())
assert release["complete"] and release["total_directions"]==110
assert not REPLAY.exists()
assert adb("emu","avd","name",capture=True).stdout.decode().splitlines()[0]=="vipi-api35-20261024"
subprocess.run(["python3","scripts/promote-bundled-lexical-008.py"],check=True,stdin=subprocess.DEVNULL)
assert sha(ROOT/"data/lexical/catalog.json")==release["bundle_sha256"]
with (ROOT/"artifacts/bundled-chat-android-build-018.log").open("x") as log:
    subprocess.run(["storage-build","--peak-bytes",str(3*1024**3),"--","bash","scripts/build-android.sh",
        "-PvipiQaAbi=x86_64",":app:assembleDebug",":app:assembleDebugAndroidTest"],
        stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,check=True)
for apk in ["android/app/build/outputs/apk/debug/app-debug.apk",
            "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"]:
    adb("install","-r","--streaming",apk)
stage="/data/local/tmp/vipi-bundled-cases-012.json"
adb("push",str(CASES),stage)
adb("shell","run-as","co.fallsoft.vipi","cp",stage,"files/bundled-conversation-cases.json")
adb("shell","rm",stage)
command=[ADB,"-s",DEVICE,"shell","am","instrument","-w","-r",
    "-e","class","co.fallsoft.vipi.BundledConversationReplayDeviceTest",
    "-e","vipiDedicatedEmulator","true","-e","vipiBundledRun","012",
    "-e","vipiCasesSha",sha(CASES),"co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner"]
with (ROOT/"artifacts/bundled-conversations-android-012.log").open("x") as log:
    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,check=True)
raw=adb("exec-out","run-as","co.fallsoft.vipi","cat","files/bundled-conversations-012.json",capture=True).stdout
with REPLAY.open("xb") as f:f.write(raw)
report=json.loads(raw)
assert report["complete"] and not report["failures"]
assert report["cases_sha256"]==sha(CASES) and report["bundled_catalog_sha256"]==release["bundle_sha256"]
assert len(report["outcomes"])==602
subprocess.run(["python3","qa/immersion/compare_bundled_replays.py","--cases",str(CASES),
    "--before","artifacts/bundled-conversations-android-011.json","--after",str(REPLAY),
    "--output","artifacts/bundled-lexical-008-android-changes.json"],check=True,stdin=subprocess.DEVNULL)
print(json.dumps(dict(complete=True,report_sha256=sha(REPLAY),catalog_sha256=release["bundle_sha256"])),flush=True)

for cases,run in [
    ("artifacts/verb-form-conversations-001/cases.json","401"),
    ("artifacts/past-verb-grammar-regressions-001/cases.json","410"),
    ("artifacts/arabic-plural-homograph-regressions-001/cases.json","311"),
    ("artifacts/arabic-plural-pronunciation-001/cases.json","321")]:
    subprocess.run(["python3","scripts/replay-bundled-conversations-android.py","--cases",cases,
        "--run",run,"--expected-catalog",release["bundle_sha256"]],check=True,stdin=subprocess.DEVNULL)
