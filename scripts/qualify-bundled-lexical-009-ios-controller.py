#!/usr/bin/env python3
"""Controller-only transfer and iOS replay after the owned pack compiler finishes."""
import hashlib,json,shlex,subprocess,time
from pathlib import Path
HOST=["ssh","-S","/home/ai/.cache/vipi-ssh-01a16e0d.sock","OZZZ-OS"]
MAC=["ssh","apple@macbook-pro"]
ROOT="/aosp/development/vipi"
MAC_ROOT="/Users/Apple/Development/vipi"
STAGE=MAC_ROOT+"/.runtime/bundled-lexical-transfer-009"
def call(host,command,data=None,capture=False):
    return subprocess.run([*host,command],input=data,stdin=subprocess.DEVNULL if data is None else None,
        stdout=subprocess.PIPE if capture else None,check=True).stdout
def read(host,path):
    return call(host,"cat "+shlex.quote(path),capture=True)
def put(host,path,data):
    code="from pathlib import Path; import sys; p=Path("+repr(path)+"); assert not p.exists(); p.write_bytes(sys.stdin.buffer.read())"
    call(host,"python3 -c "+shlex.quote(code),data)
raw=read(HOST,ROOT+"/artifacts/korean-context-release-001/receipt.json")
release=json.loads(raw)
assert release["complete"] and release["total_directions"]==110
print("Completed bundle available; transferring exact native assets to Mac.",flush=True)
code="from pathlib import Path; p=Path("+repr(STAGE)+"); p.mkdir(exist_ok=False); (p/'candidate').mkdir()"
call(MAC,"python3 -c "+shlex.quote(code))
source=subprocess.Popen([*HOST,"tar -cf - -C "+shlex.quote(ROOT+"/artifacts/bundled-lexical-009")+" ."],
    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE)
try:
    destination=subprocess.run([*MAC,"tar -xf - -C "+shlex.quote(STAGE+"/candidate")],stdin=source.stdout,check=True)
finally:
    source.stdout.close()
assert source.wait()==0,"Source transfer failed; inspect existing stage before any retry"
put(MAC,STAGE+"/release-receipt.json",raw)
for source_path,destination_path in [
    ("ios/Vipi/LexicalConcordance.swift",STAGE+"/LexicalConcordance.swift"),
    ("ios/Vipi/ContextWitnessLookup.swift",STAGE+"/ContextWitnessLookup.swift"),
    ("scripts/qualify-bundled-lexical-009-ios.py",MAC_ROOT+"/scripts/qualify-bundled-lexical-009-ios.py")]:
    put(MAC,destination_path,read(HOST,ROOT+"/"+source_path))
cases="artifacts/bundled-development-004/combined-cases.json"
expected=read(HOST,ROOT+"/"+cases)
actual=read(MAC,MAC_ROOT+"/"+cases)
assert actual==expected,"Mac retained replay inputs must match the frozen cases"
negative="artifacts/past-verb-grammar-regressions-001/cases.json"
call(MAC,"mkdir -p "+shlex.quote(MAC_ROOT+"/artifacts/past-verb-grammar-regressions-001"))
assert read(MAC,MAC_ROOT+"/"+negative)==read(HOST,ROOT+"/"+negative)
for path in ["artifacts/verb-form-conversations-001/cases.json",
    "artifacts/arabic-plural-homograph-regressions-001/cases.json","artifacts/arabic-plural-pronunciation-001/cases.json"]:
    assert read(HOST,ROOT+"/"+path)==read(MAC,MAC_ROOT+"/"+path)
call(MAC,"cd "+shlex.quote(MAC_ROOT)+" && python3 scripts/qualify-bundled-lexical-009-ios.py > artifacts/bundled-lexical-009-ios-driver.log 2>&1")
report=read(MAC,MAC_ROOT+"/artifacts/bundled-conversations-simulator-012.json")
value=json.loads(report)
assert value["complete"] and not value["failures"]
assert value["bundled_catalog_sha256"]==release["bundle_sha256"]
put(HOST,ROOT+"/artifacts/bundled-conversations-simulator-012.json",report)
call(HOST,"cd "+shlex.quote(ROOT)+" && python3 qa/immersion/compare_bundled_replays.py --cases "+cases+
    " --before artifacts/bundled-conversations-simulator-011.json --after artifacts/bundled-conversations-simulator-012.json"+
    " --output artifacts/bundled-lexical-009-simulator-changes.json")
print(json.dumps(dict(complete=True,platform="iOS simulator",report_sha256=hashlib.sha256(report).hexdigest(),
    catalog_sha256=release["bundle_sha256"],physical_device_verified=False)),flush=True)

for run in ["402","411","312","322"]:
    name="artifacts/bundled-conversations-simulator-"+run+".json"
    report=read(MAC,MAC_ROOT+"/"+name)
    value=json.loads(report)
    assert value["complete"] and not value["failures"] and value["bundled_catalog_sha256"]==release["bundle_sha256"]
    put(HOST,ROOT+"/"+name,report)
