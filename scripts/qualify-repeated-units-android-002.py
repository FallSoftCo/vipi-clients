#!/usr/bin/env python3
"""Reuse exact QA staging recovery while qualifying repeated whole units."""
from pathlib import Path
import json,hashlib,runpy
ROOT=Path("/aosp/development/vipi")
helpers=runpy.run_path(str(ROOT/"scripts/qualify-context-case-android-001.py"))
run=helpers["run"];staged_out=helpers["staged_out"];sha=helpers["sha"]
pin=json.loads((ROOT/"artifacts/repeated-unit-source-003/receipt.json").read_text())
for row in pin["files"]:assert sha(ROOT/row["path"])==row["sha256"]
log=(ROOT/"artifacts/repeated-unit-android-build-002.log").read_text()
assert "BUILD SUCCESSFUL" in log and '"exit_code": 0' in log
with staged_out("repeated-install-002"):
    run("python3","scripts/install-lexical-candidate-android.py","--run","018")
run("python3","scripts/run-lexical-candidate-android.py","--run","517","--fixture","512","--witness","506")
run("python3","scripts/run-lexical-candidate-android.py","--run","611","--fixture","600","--witness","506")
with staged_out("repeated-broad-002"):
    run("python3","scripts/replay-bundled-conversations-android.py","--run","018","--cases","artifacts/bundled-development-004/combined-cases.json",
        "--expected-catalog","6b8040ae0eacb82dded24d9cf948649551195165d3d1c12a085e17e02e847300")
print("Repeated-unit native qualification complete; exact witness restored.",flush=True)
