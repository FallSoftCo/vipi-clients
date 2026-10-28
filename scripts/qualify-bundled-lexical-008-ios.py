#!/usr/bin/env python3
"""Qualify a transferred bundle with the owned iOS simulator and native reader."""
from pathlib import Path
import hashlib,json,os,platform,shutil,subprocess,time
ROOT=Path("/Users/Apple/Development/vipi")
STAGE=ROOT/".runtime/bundled-lexical-transfer-008"
DEVICE="46CB569D-EA59-40E3-82CC-F4A0F36EDB87"
OLD_CATALOG="6c5a11fecf55a19e3969a7040a4e12a374e49ff2324328fba2fd77ae911ba2f7"
OLD_READER="52399d6bd7bda9b5bea538f46d988f21e329b2b8db32278aa11afdf8934dbfa3"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def command(*args,cwd=ROOT,capture=False):
    return subprocess.run(args,cwd=cwd,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,check=True)
def container():
    return Path(command("xcrun","simctl","get_app_container",DEVICE,"co.fallsoft.vipi","data",capture=True).stdout.decode().strip())
def main():
    assert platform.system()=="Darwin"
    os.chdir(ROOT)
    release=json.loads((STAGE/"release-receipt.json").read_text())
    candidate=STAGE/"candidate";current=ROOT/"data/lexical"
    reader=ROOT/"ios/Vipi/LexicalConcordance.swift"
    assert release["complete"] and release["total_directions"]==110
    assert sha(candidate/"catalog.json")==release["bundle_sha256"]
    assert sha(current/"catalog.json")==OLD_CATALOG and sha(reader)==OLD_READER
    witness=ROOT/"ios/Vipi/ContextWitnessLookup.swift"
    assert sha(witness)=='37a388425bb86e6ab743fc7eaab33b12d68f983cd3959156dd0e8483a0dfb7b3'
    command("python3","scripts/check-bundled-lexical.py",str(candidate))
    cases=ROOT/"artifacts/bundled-development-004/combined-cases.json"
    assert sha(cases)=="31749d51dce948d425ceb3e6d381587db35d66b8c1d4f5af5e621cc3b263b454"
    previous=STAGE/"previous-lexical-007";assert not previous.exists()
    shutil.copyfile(reader,STAGE/"previous-LexicalConcordance.swift")
    current.rename(previous)
    try:candidate.rename(current)
    except BaseException:
        previous.rename(current);raise
    shutil.copyfile(STAGE/"LexicalConcordance.swift",reader)
    shutil.copyfile(witness,STAGE/"previous-ContextWitnessLookup.swift")
    shutil.copyfile(STAGE/"ContextWitnessLookup.swift",witness)
    promotion=dict(complete=True,old_catalog_sha256=OLD_CATALOG,
        catalog_sha256=sha(current/"catalog.json"),reader_sha256=sha(reader),
        development_only=True,native_qualified=False)
    (STAGE/"promotion.json").write_text(json.dumps(promotion,indent=2)+"\n")
    documents=container()/"Documents";documents.mkdir(exist_ok=True)
    shutil.copyfile(cases,documents/"bundled-conversation-cases.json")
    (documents/"bundled-conversation-run.txt").write_text("011 "+sha(cases)+"\n")
    result=ROOT/"artifacts/bundled-conversations-simulator-011.xcresult"
    report=ROOT/"artifacts/bundled-conversations-simulator-011.json"
    assert not result.exists() and not report.exists()
    with (ROOT/"artifacts/bundled-conversations-simulator-011.log").open("x") as log:
        subprocess.run(["xcodebuild","-workspace","Vipi.xcworkspace","-scheme","VipiSimulator",
            "-configuration","Simulator","-sdk","iphonesimulator","-destination",
            "platform=iOS Simulator,id="+DEVICE+",arch=arm64","-derivedDataPath","../build/ios-simulator",
            "-parallel-testing-enabled","NO","-collect-test-diagnostics","never",
            "-only-testing:VipiCryptoTests/BundledConversationReplayTests","-resultBundlePath",str(result),
            "ARCHS=arm64","EXCLUDED_ARCHS=","CODE_SIGNING_ALLOWED=YES","CODE_SIGN_IDENTITY=-","test"],
            cwd=ROOT/"ios",stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True)
    raw=(container()/"Documents/bundled-conversations-011.json").read_bytes()
    report.write_bytes(raw);value=json.loads(raw)
    assert value["complete"] and not value["failures"] and len(value["outcomes"])==602
    assert value["cases_sha256"]==sha(cases) and value["bundled_catalog_sha256"]==release["bundle_sha256"]
    print(json.dumps(dict(complete=True,report_sha256=sha(report),catalog_sha256=release["bundle_sha256"],
        physical_device_verified=False,translation_reused=True)),flush=True)
if __name__=="__main__":
    main()
    release=json.loads((STAGE/"release-receipt.json").read_text())
    for cases,run in [
        ("artifacts/verb-form-conversations-001/cases.json","401"),
        ("artifacts/past-verb-grammar-regressions-001/cases.json","410"),
        ("artifacts/arabic-plural-homograph-regressions-001/cases.json","311"),
        ("artifacts/arabic-plural-pronunciation-001/cases.json","321")]:
        command("python3","scripts/replay-bundled-conversations-ios.py","--cases",cases,
            "--run",run,"--expected-catalog",release["bundle_sha256"])

