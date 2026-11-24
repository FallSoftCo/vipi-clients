"""Publish one explicitly selected, reviewable Vipi visual batch to the studio."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

WORK = Path("/mnt/extradrive1/vipi-builds/gallery-publication-r01")
OUTPUT = Path("/home/ai/Development/8bar-houdini/output")
SITE = "https://system76-pc.tailb77f2a.ts.net/8bar/"
SHELF = "vipi-studio-20261120/"
ART_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".html", ".pdf", ".mp4"}


def read_and_validate(path):
    batch = json.loads(path.read_text())
    assert re.fullmatch("[a-z0-9]+(?:-[a-z0-9]+)*", batch["slug"])
    assert batch["title"].strip() and batch["description"].strip() and batch["items"]
    names = set()
    for item in batch["items"]:
        src = Path(item["path"])
        assert item["label"].strip() and src.is_absolute() and src.is_file(), src
        assert src.suffix.lower() in ART_TYPES and src.name not in names, src
        names.add(src.name)
    assert Path(batch["items"][0]["path"]).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    return batch


def publish(batch):
    config = WORK / "batches.json"
    batches = json.loads(config.read_text())
    seen = {item["slug"]: item for item in batches}
    slug = batch["slug"]
    assert slug not in {"logo-concepts", "palette", "android-theme", "ios-inbox", "earlier-chat"}
    if slug in seen:
        old = {Path(i["path"]).name for i in seen[slug]["items"]}
        new = {Path(i["path"]).name for i in batch["items"]}
        assert old <= new, "Keep earlier artwork available. Use a new slug for a revision."
    for item in batch["items"]:
        src = Path(item["path"])
        existing = OUTPUT / SHELF / slug / src.name
        assert not existing.exists() or src.read_bytes() == existing.read_bytes(), (
            "Published artwork changed. Use a new revision slug.", src.name)
    seen[slug] = batch
    with tempfile.NamedTemporaryFile(dir=WORK, mode="w", delete=False) as f:
        json.dump(list(seen.values()), f, indent=2)
        temporary = f.name
    os.replace(temporary, config)
    for name in ("build_shelf.py", "update_main_gallery.py"):
        subprocess.run([sys.executable, Path(__file__).with_name(name)], check=True)
    catalog_url = SITE + "showcase-catalog.json"
    with urllib.request.urlopen(catalog_url, timeout=30) as response:
        card = next(c for c in json.load(response) if c["id"] == "vipi-studio-" + slug)
    assert len(card["downloads"]) == len(batch["items"])
    for item in batch["items"]:
        src = Path(item["path"])
        with urllib.request.urlopen(SITE + SHELF + slug + "/" + quote(src.name), timeout=25) as response:
            assert hashlib.file_digest(response, "sha256").digest() == hashlib.sha256(src.read_bytes()).digest()
    print(SITE + SHELF + "#" + slug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="JSON with slug, title, description and ordered items")
    args = parser.parse_args()
    with (WORK / ".review-publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        publish(read_and_validate(args.batch))
