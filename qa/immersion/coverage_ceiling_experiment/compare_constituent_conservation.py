#!/usr/bin/env python3
"""QA-only contained-scope shortening on frozen, previously reviewed outputs."""
import argparse
import hashlib
import json
from pathlib import Path

from compare_direct_extension import ARMS, key, mixed


def scope(span):
    return tuple(span[k] for k in ("sourceStartUTF16", "sourceEndUTF16",
                                  "targetStartUTF16", "targetEndUTF16"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = Path(__file__).with_name("constituent-conservation-freeze-r01.json")
    rows = []
    bindings = {str(plan): hashlib.sha256(plan.read_bytes()).hexdigest()}
    for provider in ("mlkit", "afrislm"):
        path = args.evidence / "chunk-agreement" / (provider + "-reference-r01.json")
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for row in json.loads(path.read_text())["rows"]:
            candidates = [c for c in row["aligned_candidates"] if set(c["arms"]) & ARMS["window"]]
            for projection in row["arms"]["window"]["projections"]:
                traces, spans = [], []
                for old in projection["spans"]:
                    a, b, ta, tb = scope(old)
                    contained = [c for c in candidates if a <= c["sourceStartUTF16"] and c["sourceEndUTF16"] <= b
                                 and scope(c)[:2] != (a, b) and scope(c)[2:] == (ta, tb)
                                 and key(c["translated"]) == key(old["translated"])]
                    if not contained:
                        new, reason = old, "unchanged_no_identical_proper_subscope"
                    else:
                        count = min(c["source_words"] for c in contained)
                        shortest = {scope(c): c for c in contained if c["source_words"] == count}
                        if len(shortest) == 1:
                            new, reason = next(iter(shortest.values())), "shortened_unique_minimal_identical_translation"
                        else:
                            new, reason = None, "abstained_ambiguous_minimal_scope"
                    traces.append(dict(before=old, after=new, reason=reason,
                                       equally_translated_proper_subscopes=contained))
                    if new is not None:
                        spans.append(new)
                rows.append(dict(id=row["id"], provider=provider, density=projection["requested_density"],
                    source=row["original"], full_reference=row["full_translation"], source_words=row["source_words"],
                    length_bin=row["length_bin"], original_visible=projection["visible"],
                    visible=mixed(row["original"], spans), traces=traces,
                    original_changed_words=sum(s["changed_source_words"] for s in projection["spans"]),
                    shortened_changed_words=sum(s["changed_source_words"] for s in spans)))
    output = dict(schema="vipi-constituent-conservation-development-1", production=False,
                  semantic_review="pending exact changed-scope review", additional_provider_calls=0,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  input_hashes=bindings, rows=rows)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    for provider in ("mlkit", "afrislm"):
        for density in (0.1, 0.25, 0.5):
            selected = [r for r in rows if r["provider"] == provider and r["density"] == density]
            print(provider, density, "changed messages", sum(any(t["before"] != t["after"] for t in r["traces"]) for r in selected))


if __name__ == "__main__":
    main()
