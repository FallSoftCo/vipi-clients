#!/usr/bin/env python3
"""Check a known English QA reply in rendered Android pixels, independently of TextView bounds.

Consumes a paired native PNG/XML capture from the isolated mobile journey suite.
Requires the host's Tesseract English model and Pillow; missing tools fail rather
than skip. This checks a supplied fixture, not translation correctness, acoustic
quality, or every possible message. Native Signal/history assertions remain separate.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET

from PIL import Image


def bounds(value):
    numbers = [int(v) for v in re.findall(r"-?\d+", value)]
    if len(numbers) != 4 or numbers[2] <= numbers[0] or numbers[3] <= numbers[1]:
        raise ValueError(f"Invalid native rectangle: {value}")
    return numbers


def inside(rect, viewport):
    return (viewport[0] <= rect[0] < rect[2] <= viewport[2]
            and viewport[1] <= rect[1] < rect[3] <= viewport[3])


def words(text):
    # OCR punctuation/emoji recognition is outside this English fixture check.
    # Accent folding here never alters the app's displayed transliteration.
    folded = "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                     if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z]+", folded)


def check(screenshot, hierarchy, expected, draft, package):
    needle = words(expected)
    if not needle:
        raise ValueError("Supply the known English fixture's expected visible reply")
    with Image.open(screenshot) as image:
        width, height = image.size
    nodes = [node for node in ET.parse(hierarchy).iter("node") if node.get("package") == package]
    editors = [n for n in nodes if n.get("class") == "android.widget.EditText" and n.get("text") == draft]
    if len(editors) != 1:
        raise ValueError("Expected exactly one native editor with the retained fixture draft")
    editor = bounds(editors[0].get("bounds", ""))
    timelines = [bounds(n.get("bounds", "")) for n in nodes
                 if n.get("scrollable") == "true" and n.get("class") != "android.widget.EditText"]
    timelines = [rect for rect in timelines if inside(rect, [0, 0, width, height])
                 and rect[3] <= editor[1] and rect[2] - rect[0] >= width * 0.9]
    if len(timelines) != 1:
        raise ValueError("Expected one actual native conversation scroll viewport above the composer")
    timeline = timelines[0]
    process = subprocess.run(["tesseract", str(screenshot), "stdout", "-l", "eng", "--psm", "11", "tsv"],
                             capture_output=True, text=True, check=True, timeout=60,
                             env={**os.environ, "OMP_THREAD_LIMIT": "2"})
    observed = []
    for row in csv.DictReader(io.StringIO(process.stdout), delimiter="\t"):
        if row["level"] != "5" or float(row["conf"]) < 45:
            continue
        x, y, w, h = (int(row[key]) for key in ("left", "top", "width", "height"))
        rect = [x, y, x + w, y + h]
        if h < 10 or not inside(rect, timeline):
            continue
        for word in words(row["text"]):
            observed.append({"word": word, "rect": rect, "confidence": float(row["conf"])})
    matches = [observed[i:i + len(needle)] for i in range(len(observed) - len(needle) + 1)
               if [w["word"] for w in observed[i:i + len(needle)]] == needle]
    digest = lambda path: hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()
    return {"passed": len(matches) == 1, "method": "actual_screenshot_ocr_inside_native_timeline_above_composer",
            "screenshot": str(screenshot), "screenshot_sha256": digest(screenshot),
            "hierarchy": str(hierarchy), "hierarchy_sha256": digest(hierarchy),
            "pixels": [width, height], "timeline": timeline, "editor": editor,
            "expected_words": needle, "observed_words_in_timeline": observed, "matches": matches,
            "native_paragraph_bounds_used_as_pixel_evidence": False,
            "limits": "Known English fixture only; does not verify emoji shape or arbitrary translation quality."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--hierarchy", required=True, type=Path)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--package", default="co.fallsoft.vipi.sourcecontextqa")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Keep the original observation; use a fresh result path")
    result = check(args.screenshot, args.hierarchy, args.expected, args.draft, args.package)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "receipt": str(args.output), "timeline": result["timeline"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
