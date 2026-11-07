#!/usr/bin/env python3
"""Frozen, licensed conversational evaluation sample; never training input.

Google Taskmaster-2 (2020), CC BY 4.0, human Wizard-of-Oz conversations.
Spoken user turns are transcription-reviewed; this is not casual friends' chat.
One turn per dialog, 200 total across seven domains, deterministic hash ordering.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

COMMIT = "d92cb6af3005f1dc09c39e75e7daf4a04905e00b"
BLOBS = {
    "flights": "21c0317c583f3533e517a4e500aea7979de9e513",
    "food-ordering": "1637d76fc83ad7bd20814f8c11b9462c77af1cfc",
    "hotels": "5d68cd83f03a647b16b6c26dc298194b1532b99c",
    "movies": "4d0112272ce72d7b954f2a5a2a2b3d077513382c",
    "music": "0463a81fec65fe7a708384a1b0f8a29ed4530953",
    "restaurant-search": "1a82c985f43d0e2390b1049e279352c6e523ce4c",
    "sports": "e61ae729224b24c3ab6c812473396a93c78d8c80",
}
PREFIX = f"https://raw.githubusercontent.com/google-research-datasets/Taskmaster/{COMMIT}/TM-2-2020/"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fetch(path, suffix):
    if path.exists():
        return path.read_bytes()
    with urllib.request.urlopen(PREFIX + suffix, timeout=45) as response:
        raw = response.read(30_000_001)
    if len(raw) > 30_000_000:
        raise ValueError("source exceeds declared 30 MB per-file bound")
    temporary = path.with_suffix(".partial")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite frozen sample")
    args.source_dir.mkdir(parents=True, exist_ok=True)
    readme = fetch(args.source_dir / "README.md", "README.md")
    if b"Creative Commons Attribution 4.0 License" not in readme:
        raise ValueError("expected explicit source license absent")
    samples, receipts = [], []
    for index, (domain, expected_blob) in enumerate(BLOBS.items()):
        raw = fetch(args.source_dir / (domain + ".json"), "data/" + domain + ".json")
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != expected_blob:
            raise ValueError("pinned upstream source blob mismatch: " + domain)
        dialogs = json.loads(raw)
        choices = []
        for dialog in dialogs:
            turns = [turn for turn in dialog["utterances"] if turn["speaker"] == "USER" and turn["text"].strip()]
            if not turns:
                continue
            turn = min(turns, key=lambda row: digest(("vipi-tm2-turn-r01:" + dialog["conversation_id"] + ":" + str(row["index"])).encode()))
            identifier = "tm2-" + dialog["conversation_id"] + "-" + str(turn["index"])
            context = [{"speaker": row["speaker"], "text": row["text"]} for row in dialog["utterances"] if row["index"] < turn["index"]][-2:]
            choices.append({"id": identifier, "text": turn["text"], "domain": domain,
                            "conversation_id": dialog["conversation_id"], "turn_index": turn["index"],
                            "assessment_context_only": context})
        choices.sort(key=lambda row: digest(("vipi-tm2-dialog-r01:" + row["conversation_id"]).encode()))
        count = 29 if index < 4 else 28
        selected = choices[:count]
        assert len(selected) == count
        samples.extend(selected)
        receipts.append({"domain": domain, "url": PREFIX + "data/" + domain + ".json", "bytes": len(raw),
                         "sha256": digest(raw), "git_blob": blob, "dialogs": len(dialogs), "sampled": count})
        print(domain, len(raw), count, flush=True)
    assert len(samples) == 200 and len({row["conversation_id"] for row in samples}) == 200
    cases = [{**row, "source": "en", "target": target} for target in ("sw", "es") for row in samples]
    value = {"schema": "vipi-modern-conversation-evaluation-1", "cases": cases, "upstream_commit": COMMIT,
             "runner_sha256": digest(Path(__file__).read_bytes()), "sources": receipts,
             "readme_url": PREFIX + "README.md", "readme_sha256": digest(readme),
             "license": "CC BY 4.0", "attribution": "Bill Byrne, Karthik Krishnamoorthi, Saravanan Ganesh, Amit Dubey, Kyu-Young Kim and Andy Cedilnik, Google LLC. Taskmaster-2 (2020).",
             "method": "User turns only; one hash-selected turn per dialog, then hash-order dialogs; 29 each flights/food/hotels/movies and 28 each music/restaurants/sports. No outcome selection.",
             "limitations": "Human task/search/recommendation conversations with transcribed speech; not natural peer-to-peer chat. No bilingual gold labels. Historical model/dictionary training overlap unmeasured.",
             "training_use": False, "pack_building_use": False}
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print("protocol", digest(args.output.read_bytes()), len(cases), flush=True)


if __name__ == "__main__":
    main()
