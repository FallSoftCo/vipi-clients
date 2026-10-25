#!/usr/bin/env python3
"""Stage only public, signed QA packs and a validated Apple capture on the iPad."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

root = Path("/Users/Apple/Development/vipi")
device = "7B6D180F-1D57-5036-8E42-C057698FBAB2"
simulator = "46CB569D-EA59-40E3-82CC-F4A0F36EDB87"
container = Path(subprocess.check_output(["xcrun", "simctl", "get_app_container", simulator,
                                        "co.fallsoft.vipi", "data"], text=True).strip())
packs = container / "Documents/bilingual-qa/packs-005"
capture = root / "artifacts/ipad-translation-011-capture.json"
data = json.loads(capture.read_bytes())
assert data["finished"] and data["network_absence_verified"] and len(data["results"]) == 90
assert packs.is_dir()
stage = root / "artifacts/ipad-language-stage-001"
stage.mkdir(exist_ok=False)
receipt = {"public_fixture_data_only": True, "packs": 90, "copy_completed": False,
           "native_signature_and_database_hash_verification": "pending native install test"}
start = time.monotonic()
base = ["xcrun", "devicectl", "device", "copy", "to", "--device", device,
        "--domain-type", "appDataContainer", "--domain-identifier", "co.fallsoft.vipi", "--quiet"]
subprocess.run(base + ["--source", str(packs), "--destination", "Documents/bilingual-qa/packs-005",
                       "--json-output", str(stage / "copy-packs.json")], check=True)
for filename, text in {"run-id.txt": "005\n", "translation-report.txt": "ipad-translation-011-capture.json\n",
                       "report-name.txt": "bilingual-ipad-apple-001.json\n"}.items():
    file = stage / filename; file.write_text(text)
    subprocess.run(base + ["--source", str(file), "--destination", "Documents/bilingual-qa/" + filename], check=True)
subprocess.run(base + ["--source", str(capture), "--destination", "Documents/bilingual-qa/" + capture.name], check=True)
receipt.update(copy_completed=True, elapsed_s=time.monotonic() - start,
               capture_sha256=hashlib.sha256(capture.read_bytes()).hexdigest())
(stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
