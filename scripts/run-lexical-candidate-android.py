#!/usr/bin/env python3
"""Replay a pinned candidate on the owned emulator without clearing app data."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path("/aosp/development/vipi")
ADB=["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb","-s","emulator-5620"]
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def adb(*args):
    return subprocess.run(ADB+list(args),stdin=subprocess.DEVNULL,capture_output=True,check=True).stdout
def main():
    p=argparse.ArgumentParser()
    for name in ("run","fixture","witness"):p.add_argument("--"+name,required=True)
    a=p.parse_args()
    assert all(len(v)==3 and v.isdigit() for v in (a.run,a.fixture,a.witness))
    assert adb("emu","avd","name").decode().splitlines()[0]=="vipi-api35-20261024"
    fixture=ROOT/("artifacts/lexical-qualification-"+a.fixture)
    manifest=json.loads((fixture/"manifest.json").read_text())
    assert sha(fixture/"cases.json")==manifest["cases_sha256"]
    witness=ROOT/("artifacts/context-witnesses-"+a.witness)/"witnesses.sqlite"
    pin=json.loads(witness.with_name("receipt.json").read_text())
    assert pin["complete"] and sha(witness)==pin["sha256"]
    report=ROOT/("artifacts/lexical-coverage-android-"+a.run+".json")
    log=report.with_suffix(".log")
    assert not report.exists() and not log.exists()
    root="files/"+fixture.name
    adb("shell","run-as","co.fallsoft.vipi","mkdir","-p",root)
    for name in ("manifest.json","cases.json"):
        destination=root+"/"+name
        with (fixture/name).open("rb") as stream:
            subprocess.run(ADB+["shell","run-as co.fallsoft.vipi sh -c 'cat > "+destination+"'"],stdin=stream,check=True,capture_output=True)
        assert adb("shell","run-as","co.fallsoft.vipi","sha256sum",destination).decode().split()[0]==sha(fixture/name)
    for row in manifest["shards"]:
        name=row["language"]+".sqlite";destination=root+"/"+name
        assert sha(fixture/name)==row["sha256"]
        if subprocess.run(ADB+["shell","run-as","co.fallsoft.vipi","test","-f",destination],stdin=subprocess.DEVNULL,capture_output=True).returncode:
            original="files/lexical-qualification-501/"+name
            assert adb("shell","run-as","co.fallsoft.vipi","sha256sum",original).decode().split()[0]==row["sha256"]
            adb("shell","run-as","co.fallsoft.vipi","ln","-s","../lexical-qualification-501/"+name,destination)
        assert adb("shell","run-as","co.fallsoft.vipi","sha256sum",destination).decode().split()[0]==row["sha256"]
    assert adb("shell","run-as","co.fallsoft.vipi","sha256sum","files/context-witnesses-"+a.witness+".sqlite").decode().split()[0]==pin["sha256"]
    # Verify both actual installed packages, not merely local build outputs.
    packages=[]
    for package,path in [("co.fallsoft.vipi","debug/app-debug.apk"),("co.fallsoft.vipi.test","androidTest/debug/app-debug-androidTest.apk")]:
        installed=adb("shell","pm","path",package).decode().strip().removeprefix("package:")
        assert "\n" not in installed and installed.startswith("/data/app/")
        actual=adb("shell","sha256sum",installed).decode().split()[0]
        assert actual==sha(ROOT/"android/app/build/outputs/apk"/path)
        packages.append(dict(package=package,sha256=actual))
    with log.open("x") as stream:
        subprocess.run(ADB+["shell","am","instrument","-w","-r","-e","class","co.fallsoft.vipi.LexicalCoverageDeviceTest",
            "-e","vipiDedicatedEmulator","true","-e","vipiLexicalRun",a.run,"-e","vipiLexicalFixture",a.fixture,
            "-e","vipiWitnessSha",pin["sha256"],"-e","vipiWitnessRevision",a.witness,
            "co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner"],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,check=True)
    report.write_bytes(adb("exec-out","run-as","co.fallsoft.vipi","cat","files/lexical-coverage-"+a.run+".json"))
    value=json.loads(report.read_text())
    assert value["complete"] and value["passed"] and not value["failures"] and value["run"]==a.run
    assert value["manifest_sha256"]==sha(fixture/"manifest.json") and value["witness_sha256"]==pin["sha256"]
    receipt=dict(complete=True,report_sha256=sha(report),packages=packages,cases=len(value["outcomes"]),production_promoted=False)
    report.with_name(report.stem+"-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt),flush=True)
if __name__=="__main__":main()
