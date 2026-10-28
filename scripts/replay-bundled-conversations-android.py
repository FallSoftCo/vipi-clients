#!/usr/bin/env python3
"""Replay fixed sentence pairs through the owned Android emulator's bundled reader."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path("/aosp/development/vipi")
ADB="/aosp/ozzz-android-toolchain/sdk/platform-tools/adb"
DEVICE="emulator-5620"
def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def adb(*args):
    return subprocess.run([ADB,"-s",DEVICE,*args],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,check=True).stdout
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases",type=Path,required=True)
    parser.add_argument("--run",required=True)
    parser.add_argument("--expected-catalog",required=True)
    args=parser.parse_args()
    assert args.run.isdigit()
    cases=args.cases.resolve();values=json.loads(cases.read_text())
    count=len(values if isinstance(values,list) else values["cases"])
    assert count>0 and sha(ROOT/"data/lexical/catalog.json")==args.expected_catalog
    assert adb("emu","avd","name").decode().splitlines()[0]=="vipi-api35-20261024"
    report=ROOT/("artifacts/bundled-conversations-android-"+args.run+".json")
    log=report.with_suffix(".log")
    assert not report.exists() and not log.exists()
    stage="/data/local/tmp/vipi-bundled-cases-"+args.run+".json"
    adb("push",str(cases),stage)
    adb("shell","run-as","co.fallsoft.vipi","cp",stage,"files/bundled-conversation-cases.json")
    adb("shell","rm",stage)
    with log.open("x") as stream:
        subprocess.run([ADB,"-s",DEVICE,"shell","am","instrument","-w","-r",
            "-e","class","co.fallsoft.vipi.BundledConversationReplayDeviceTest",
            "-e","vipiDedicatedEmulator","true","-e","vipiBundledRun",args.run,
            "-e","vipiCasesSha",sha(cases),"co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner"],
            stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,check=True)
    raw=adb("exec-out","run-as","co.fallsoft.vipi","cat","files/bundled-conversations-"+args.run+".json")
    with report.open("xb") as stream:stream.write(raw)
    value=json.loads(raw)
    assert value["run"]==args.run
    assert value["complete"] and not value["failures"] and len(value["outcomes"])==count
    assert value["cases_sha256"]==sha(cases) and value["bundled_catalog_sha256"]==args.expected_catalog
    print(json.dumps(dict(complete=True,report_sha256=sha(report),cases=count,
        catalog_sha256=args.expected_catalog,physical_device_verified=False,translation_reused=True)),flush=True)
if __name__=="__main__":main()
