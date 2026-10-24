#!/usr/bin/env python3
"""Acquire one versioned upstream source, then retain selected-language entries.

Runs on OZZZ-OS under storage-build. Never expands the 24.8GB raw JSONL file.
The retained gzip and response metadata pin exact provenance for pack compilation.
"""
import gzip
import hashlib
import json
from pathlib import Path
import socket
import urllib.request

assert socket.gethostname() == "ozzz-aosp"
root = Path("/aosp/development/vipi/vendor-research/dictionaries/wiktextract-20261021")
root.mkdir(parents=True, exist_ok=True)
url = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
expected_bytes = 3_082_192_147
expected_etag = '"6ad8a097-b7b68513"'
source = root / "raw-wiktextract-data.jsonl.gz"
manifest = root / "source.json"
if not source.exists():
    temp = source.with_suffix(".partial")
    request = urllib.request.Request(url, headers={"If-Match": expected_etag})
    with urllib.request.urlopen(request, timeout=90) as response:
        assert response.headers.get("ETag") == expected_etag
        assert int(response.headers["Content-Length"]) == expected_bytes
        digest = hashlib.sha256(); count = 0
        with temp.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                assert count <= expected_bytes
                output.write(chunk); digest.update(chunk)
        assert count == expected_bytes
        metadata = {"url": url, "bytes": count, "sha256": digest.hexdigest(), "etag": expected_etag,
            "last_modified": response.headers.get("Last-Modified"), "wiktionary_dump": "2026-10-01",
            "extraction": "2026-10-21", "license_source": "https://kaikki.org/dictionary/",
            "copyright_source": "https://en.wiktionary.org/wiki/Wiktionary:Copyrights"}
    temp.rename(source); manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"downloaded_bytes": count, "sha256": digest.hexdigest()}), flush=True)
else:
    metadata = json.loads(manifest.read_text())
    assert source.stat().st_size == expected_bytes

output = root / "ten-languages.jsonl.gz"
if output.exists():
    raise SystemExit("Filtered source already exists; do not overwrite a completed extraction")
codes = {"en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko"}
counts = {code: 0 for code in codes}
temporary = output.with_suffix(".partial")
with gzip.open(source, "rt", encoding="utf-8") as lines, gzip.open(temporary, "wt", encoding="utf-8", compresslevel=3) as selected:
    for index, line in enumerate(lines, 1):
        entry = json.loads(line)
        code = entry.get("lang_code")
        if code in codes and entry.get("pos") in {"noun", "verb", "adj", "adv", "intj"}:
            # Keep original entry content, including senses, word forms and
            # supplied romanization. No inferred translations are asserted here.
            selected.write(line); counts[code] += 1
        if index % 1_000_000 == 0:
            print(json.dumps({"source_entries_read": index, "selected": counts}), flush=True)
        if temporary.stat().st_size > 2_000_000_000:
            raise RuntimeError("Filtered source exceeded declared storage estimate")
temporary.rename(output)
(root / "extraction.json").write_text(json.dumps({"entries": counts, "compressed_bytes": output.stat().st_size,
    "source_sha256": metadata["sha256"], "status": "raw_selection_not_a_language_pack"}, indent=2) + "\n")
print(json.dumps({"completed": str(output), "entries": counts, "bytes": output.stat().st_size}), flush=True)
