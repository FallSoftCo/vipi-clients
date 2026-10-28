#!/usr/bin/env python3
"""Controller-only transfer and iOS replay after the owned pack compiler finishes."""
import hashlib,json,shlex,subprocess,time
from pathlib import Path
HOST=["ssh","-S","/home/ai/.cache/vipi-ssh-01a16e0d.sock","OZZZ-OS"]
MAC=["ssh","apple@macbook-pro"]
ROOT="/aosp/development/vipi"
HOME="/Users/Apple/Development/vipi"
STAGE=HOME+"/.runtime/bundled-lexical-transfer-004"
def call(host,command,data=None,capture=False):
    return subprocess.run([*host,command],input=data,stdin=subprocess.DEVNULL if data is None else None,
        stdout=subprocess.PIPE if capture else None,check=True).stdout
def read(host,path):
    return call(host,"cat "+shlex.quote(path),capture=True)
def put(host,path,data):
    code="from pathlib import Path; import sys; p=Path("+repr(path)+"); assert not p.exists(); p.write_bytes(sys.stdin.buffer.read())"
    call(host,"python3 -c "+shlex.quote(code),data)
deadline=time.monotonic()+4*3600
while True:
    code="from pathlib import Path; import json; p=Path("+repr(ROOT+"/artifacts/context-agreement-release-001/receipt.json")+"); print(p.read_text() if p.exists() else 'null')"
    raw=call(HOST,"python3 -c "+shlex.quote(code),capture=True)
    release=json.loads(raw)
    if release is not None:break
    state=json.loads(read(HOST,ROOT+"/artifacts/coverage-expansion-004-run-001/state.json"))
    assert state["stage"]!="failed",state
    assert time.monotonic()<deadline,"Owned release wait expired"
    time.sleep(20)
assert release["complete"] and release["directions"]==110
print("Completed bundle available; transferring exact native assets to Mac.",flush=True)
code="from pathlib import Path; p=Path("+repr(STAGE)+"); p.mkdir(exist_ok=False); (p/'candidate').mkdir()"
call(MAC,"python3 -c "+shlex.quote(code))
source=subprocess.Popen([*HOST,"tar -cf - -C "+shlex.quote(ROOT+"/artifacts/bundled-lexical-004")+" ."],
    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE)
try:
    destination=subprocess.run([*MAC,"tar -xf - -C "+shlex.quote(STAGE+"/candidate")],stdin=source.stdout,check=True)
finally:
    source.stdout.close()
assert source.wait()==0,"Source transfer failed; inspect existing stage before any retry"
put(MAC,STAGE+"/release-receipt.json",raw)
for source_path,destination_path in [
    ("ios/Vipi/LexicalConcordance.swift",STAGE+"/LexicalConcordance.swift"),
    ("scripts/qualify-bundled-lexical-004-ios.py",HOME+"/scripts/qualify-bundled-lexical-004-ios.py")]:
    put(MAC,destination_path,read(HOST,ROOT+"/"+source_path))
cases="artifacts/bundled-development-004/combined-cases.json"
expected=read(HOST,ROOT+"/"+cases)
actual=read(MAC,HOME+"/"+cases)
assert actual==expected,"Mac retained replay inputs must match the frozen cases"
call(MAC,"cd "+shlex.quote(HOME)+" && python3 scripts/qualify-bundled-lexical-004-ios.py > artifacts/bundled-lexical-004-ios-driver.log 2>&1")
report=read(MAC,HOME+"/artifacts/bundled-conversations-simulator-007.json")
value=json.loads(report)
assert value["complete"] and not value["failures"]
assert value["bundled_catalog_sha256"]==release["bundle_sha256"]
put(HOST,ROOT+"/artifacts/bundled-conversations-simulator-007.json",report)
call(HOST,"cd "+shlex.quote(ROOT)+" && python3 qa/immersion/compare_bundled_replays.py --cases "+cases+
    " --before artifacts/bundled-conversations-simulator-006.json --after artifacts/bundled-conversations-simulator-007.json"+
    " --output artifacts/bundled-lexical-004-simulator-changes.json")
print(json.dumps(dict(complete=True,platform="iOS simulator",report_sha256=hashlib.sha256(report).hexdigest(),
    catalog_sha256=release["bundle_sha256"],physical_device_verified=False)),flush=True)
