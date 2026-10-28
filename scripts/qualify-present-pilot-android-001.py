#!/usr/bin/env python3
"""Evaluate present forms on the owned emulator without changing bundled packs."""
from pathlib import Path
from contextlib import closing
import hashlib,json,os,shlex,sqlite3,subprocess,time
R=Path("/aosp/development/vipi")
SOURCE=R/"artifacts/context-witnesses-present-pilot-003"
RUNTIME=R/"artifacts/context-witnesses-503"
FIXTURE=R/"artifacts/lexical-qualification-501"
OUT=R/"artifacts/present-native-qualification-001"
ADB=["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb","-s","emulator-5620"]
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
def adb(*args):
    return subprocess.check_output(ADB+list(args),stdin=subprocess.DEVNULL)
def put(source,target):
    exists=subprocess.run(ADB+["shell","run-as","co.fallsoft.vipi","test","-e",target],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL).returncode==0
    if exists:
        assert adb("exec-out","run-as","co.fallsoft.vipi","sha256sum",target).decode().split()[0]==sha(source)
        return
    with source.open("rb") as stream:
        subprocess.run(ADB+["shell","-T",shlex.join(["run-as","co.fallsoft.vipi","sh","-c","cat > "+shlex.quote(target)])],
            stdin=stream,check=True)
    assert adb("exec-out","run-as","co.fallsoft.vipi","sha256sum",target).decode().split()[0]==sha(source)
def main():
    OUT.mkdir(exist_ok=False)
    deadline=time.monotonic()+7200
    while not (SOURCE/"receipt.json").exists():
        assert time.monotonic()<deadline
        time.sleep(5)
    receipt=json.loads((SOURCE/"receipt.json").read_text())
    source=SOURCE/"witnesses.sqlite"
    assert receipt["complete"] and sha(source)==receipt["sha256"]
    baseline=R/"artifacts/context-witnesses-020/witnesses.sqlite"
    pin=json.loads(baseline.with_name("receipt.json").read_text())
    assert sha(baseline)==pin["sha256"]
    with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-16384")
        db.execute("ATTACH DATABASE ? AS old",(baseline.resolve().as_uri()+"?mode=ro&immutable=1",))
        condition="((source='en' AND target='es') OR (source='es' AND target='en')) AND word NOT LIKE '@present:%'"
        select="SELECT source,target,word,counterpart,cue,support,total FROM "
        removed=db.execute(select+"old.witnesses WHERE "+condition+" EXCEPT "+select+"main.witnesses WHERE "+condition+" LIMIT 20").fetchall()
        added=db.execute(select+"main.witnesses WHERE "+condition+" EXCEPT "+select+"old.witnesses WHERE "+condition+" LIMIT 20").fetchall()
        audit=dict(complete=True,legacy_rules_exactly_preserved=not added and not removed,
            old_sha256=pin["sha256"],candidate_sha256=receipt["sha256"],sample_added=added,sample_removed=removed)
        save(OUT/"legacy-rule-audit.json",audit)
        assert audit["legacy_rules_exactly_preserved"],"Unexpected legacy rule changes; inspect audit before native qualification"
        RUNTIME.mkdir(exist_ok=False)
        with closing(sqlite3.connect(RUNTIME/"witnesses.sqlite")) as runtime:
            for name in ["metadata","witnesses"]:
                runtime.execute(db.execute("SELECT sql FROM sqlite_master WHERE name=?",(name,)).fetchone()[0])
                rows=db.execute("SELECT * FROM "+name)
                count=len(rows.description)
                runtime.executemany("INSERT INTO "+name+" VALUES ("+",".join("?" for _ in range(count))+")",rows)
            runtime.commit()
            assert runtime.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    runtime=RUNTIME/"witnesses.sqlite"
    save(RUNTIME/"receipt.json",dict(complete=True,sha256=sha(runtime),bytes=runtime.stat().st_size,
        authoring_source_sha256=receipt["sha256"],qa_only=True,production_promoted=False))
    (RUNTIME/"ATTRIBUTION.txt").write_text((SOURCE/"ATTRIBUTION.txt").read_text())
    assert adb("emu","avd","name").decode().splitlines()[0]=="vipi-api35-20261024"
    assert "BUILD SUCCESSFUL" in (R/"artifacts/present-verb-android-build-002.log").read_text()
    for apk in ["android/app/build/outputs/apk/debug/app-debug.apk","android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"]:
        subprocess.run(ADB+["install","-r","--streaming",str(R/apk)],stdin=subprocess.DEVNULL,check=True)
    remote="files/lexical-qualification-501"
    adb("shell","run-as","co.fallsoft.vipi","mkdir","-p",remote)
    for name in ["en.sqlite","es.sqlite","manifest.json","cases.json"]:put(FIXTURE/name,remote+"/"+name)
    put(runtime,"files/context-witnesses-503.sqlite")
    subprocess.run(["python3","qa/immersion/run_android_lexical.py","--run","501","--fixture","501",
        "--witness","503","--shared-fixture","501"],cwd=R,stdin=subprocess.DEVNULL,check=True)
    report=R/"artifacts/lexical-coverage-android-501.json"
    value=json.loads(report.read_text())
    assert value["complete"] and value["passed"] and value["run"]=="501"
    save(OUT/"android-receipt.json",dict(complete=True,report_sha256=sha(report),runtime_sha256=sha(runtime),
        fixture_manifest_sha256=sha(FIXTURE/"manifest.json"),cases=len(value["outcomes"]),
        native_grammar_checks=True,production_promoted=False,semantic_accuracy_claim=False))
    print(json.dumps(dict(complete=True,cases=len(value["outcomes"]),report_sha256=sha(report))),flush=True)
if __name__=="__main__":main()
