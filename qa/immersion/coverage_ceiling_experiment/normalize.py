#!/usr/bin/env python3
"""Evaluation-only SMS spelling arm, with reversible UTF-16 span provenance.

Never changes sent/stored messages. No model or target text informs these rules.
Ambiguous numerals, ur/your/you're, rite/right, hear/here and names stay intact.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

ALIASES = {
    "u": "you", "pls": "please", "plz": "please", "tmr": "tomorrow",
    "tmrw": "tomorrow", "tomo": "tomorrow", "tonite": "tonight",
    "msg": "message", "txt": "text", "thx": "thanks", "ppl": "people",
    "btw": "by the way",
}
PROTECTED = re.compile(r"https?://\S+|www\.\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|```[\s\S]*?```|`[^`]*`|\"[^\"]*\"|“[^”]*”|(?<!\w)'[^'\n]*'(?!\w)|\b[\w.-]+\.(?:com|org|net|app|co|uk)\b", re.I)
TOKEN = re.compile(r"(?<![\w'’])(?:" + "|".join(sorted(ALIASES, key=len, reverse=True)) + r")(?![\w'’])", re.I)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def u16(text):
    return len(text.encode("utf-16-le")) // 2


def normalize(text):
    protected = [(m.start(), m.end()) for m in PROTECTED.finditer(text)]
    edits = []
    for match in TOKEN.finditer(text):
        before, original = text[:match.start()], match.group()
        if any(a < match.end() and match.start() < b for a, b in protected):
            continue
        # Preserve capitalized names/acronyms except sentence-initial title case.
        initial = not before.strip() or bool(re.search(r"[.!?]\s*$", before))
        if original != original.lower() and not (initial and original == original.capitalize()):
            continue
        # A named letter, file type, path component or variable is not pronoun u.
        if original.lower() == "u" and (re.search(r"(?:letter|variable|character|press|key|type)\s+$", before, re.I)
                                          or re.match(r"\s*(?:=|[+*/])", text[match.end():])):
            continue
        if (match.start() and text[match.start() - 1] in "/\\_") or (match.end() < len(text) and text[match.end()] in "/\\_"):
            continue
        if re.search(r"\w\.$", before) or re.match(r"\.\w", text[match.end():]):
            continue
        replacement = ALIASES[original.lower()]
        if original[:1].isupper():
            replacement = replacement.capitalize()
        edits.append((match.start(), match.end(), replacement, "expanded_sms_form"))
    # U+0092 is a legacy Windows apostrophe decoded as a control character.
    for match in re.finditer(r"(?<=[A-Za-z])\x92(?=[A-Za-z])", text):
        if not any(a < match.end() and match.start() < b for a, b in protected):
            edits.append((match.start(), match.end(), "’", "legacy_apostrophe"))
    edits.sort()
    parts, segments, cursor, target_units = [], [], 0, 0
    for start, end, replacement, reason in edits + [(len(text), len(text), "", "end")]:
        if start > cursor:
            same = text[cursor:start]
            segments.append({"original_range": [u16(text[:cursor]), u16(text[:start])],
                             "normalized_range": [target_units, target_units + u16(same)], "kind": "unchanged"})
            parts.append(same); target_units += u16(same)
        if end > start:
            segments.append({"original_range": [u16(text[:start]), u16(text[:end])],
                             "normalized_range": [target_units, target_units + u16(replacement)],
                             "kind": reason, "original": text[start:end], "replacement": replacement})
            parts.append(replacement); target_units += u16(replacement)
        cursor = end
    return {"text": "".join(parts), "segments": segments, "changed": bool(edits)}


def verify_mapping(original, result):
    old, new = original.encode("utf-16-le"), result["text"].encode("utf-16-le")
    a = b = 0
    for segment in result["segments"]:
        x, y = segment["original_range"], segment["normalized_range"]
        assert x[0] == a and y[0] == b and x[1] >= a and y[1] >= b
        if segment["kind"] == "unchanged":
            assert old[x[0]*2:x[1]*2] == new[y[0]*2:y[1]*2]
        else:
            assert old[x[0]*2:x[1]*2].decode("utf-16-le") == segment["original"]
            assert new[y[0]*2:y[1]*2].decode("utf-16-le") == segment["replacement"]
        a, b = x[1], y[1]
    assert (a, b) == (len(old)//2, len(new)//2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained protocol")
    cases, counts = [], collections.Counter()
    for case in json.loads(args.protocol.read_text())["cases"]:
        normalized = normalize(case["text"])
        verify_mapping(case["text"], normalized)
        if normalized["changed"]:
            cases.append({**case, "text": normalized["text"], "original_text": case["text"],
                          "original_id": case["id"], "normalization_segments": normalized["segments"]})
            counts[case["target"]] += 1
    value = {"schema": "vipi-normalized-conversation-protocol-1", "cases": cases,
             "source_protocol_sha256": sha(args.protocol), "normalizer_sha256": sha(__file__),
             "production_use": False, "review_status": "rules frozen before actual normalized provider capture; source cases already diagnostic",
             "summary": dict(counts), "unchanged_cases_excluded": True}
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"cases": len(cases), "by_target": dict(counts), "sha256": sha(args.output)}))


if __name__ == "__main__":
    main()
