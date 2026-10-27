#!/usr/bin/env python3
"""Report per-direction availability and native token depth with a fixed denominator."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from analyze_lexical_qualification import read, sha, identity, quantile

CONVERSATION_DATASETS=("sms","multi3woz","xpersona","liva-sw-explicit-replay")
REFERENCE_DATASETS=("flores200-human-reference-diagnostic",)
DEPTH_LEVELS=(.10,.25,.50)

def depth(case, outcome):
    """Use native UTF-16 word ranges; keep partial carrier replacements explicit."""
    if "source_token_ranges" not in outcome:
        return None
    tokens=outcome["source_token_ranges"]
    text=case["original"].encode("utf-16-le")
    previous=0
    for start,end in tokens:
        assert isinstance(start,int) and isinstance(end,int)
        assert previous<=start<end<=len(text)//2
        # Native tokenizers own the denominator; Python and Foundation have
        # different Unicode alphabetic sets. Validate geometry without reclassifying.
        assert text[2*start:2*end].decode("utf-16-le")
        previous=end
    spans=sorted((s["start"],s["end"]) for s in outcome["combined_spans"])
    for i,(start,end) in enumerate(spans):
        assert i==0 or spans[i-1][1]<=start, "Selected spans overlap"
    touched=full=0
    for start,end in tokens:
        intersections=[(max(start,a),min(end,b)) for a,b in spans if a<end and b>start]
        covered=sum(b-a for a,b in intersections)
        touched+=covered>0
        full+=covered==end-start
    return dict(tokens=len(tokens),touched=touched,fully_covered=full,
                touched_fraction=touched/len(tokens) if tokens else 0.,
                fully_covered_fraction=full/len(tokens) if tokens else 0.)

def summarize(rows, cases):
    if not rows:
        return dict(status="unmeasured",messages=0)
    availability=sum(bool(r["combined_spans"]) for r in rows)
    values=[depth(cases[identity(r)],r) for r in rows]
    result=dict(status="measured_diagnostic",messages=len(rows),
        distinct_source_messages=len({(r["dataset"],r["id"],r["source"]) for r in rows}),
        messages_with_span=availability,availability_percent=round(100*availability/len(rows),3),
        availability_floor_met=availability/len(rows)>=.9,
        identifier_rejected_messages=sum(not r["identifier_guard"] for r in rows),
        baseline_loss_messages=sum(not r["baseline_retained"] for r in rows),
        depth_measured_messages=sum(v is not None for v in values),
        semantic_accuracy=None,independent_semantic_acceptance=False)
    if all(v is not None for v in values):
        result["depth"]=dict(
            messages_without_native_words=sum(v["tokens"]==0 for v in values),
            native_word_tokens=sum(v["tokens"] for v in values),
            tokens_touched=sum(v["touched"] for v in values),
            tokens_fully_covered=sum(v["fully_covered"] for v in values),
            message_touched_percent_p10=quantile([100*v["touched_fraction"] for v in values],.1),
            message_touched_percent_median=quantile([100*v["touched_fraction"] for v in values],.5),
            message_fully_covered_percent_median=quantile([100*v["fully_covered_fraction"] for v in values],.5),
            messages_at_depth={
                str(int(level*100)):dict(
                    touched=sum(v["touched_fraction"]>=level for v in values),
                    fully_covered=sum(v["fully_covered_fraction"]>=level for v in values),
                    touched_percent=round(100*sum(v["touched_fraction"]>=level for v in values)/len(rows),3),
                    fully_covered_percent=round(100*sum(v["fully_covered_fraction"]>=level for v in values)/len(rows),3))
                for level in DEPTH_LEVELS})
    else:
        result["depth"]=None
    return result

def require_coverage_population(manifest):
    if manifest.get("evaluation_scope")=="targeted-regression-only":
        raise ValueError("A targeted regression fixture cannot establish conversational coverage")


def scorecard(fixture, report_path):
    manifest=json.loads((fixture/"manifest.json").read_text())
    require_coverage_population(manifest)
    validation,actual=read(fixture,report_path)
    cases={identity(r):r for r in json.loads((fixture/"cases.json").read_text())}
    languages=sorted(s["language"] for s in manifest["shards"])
    groups=defaultdict(list)
    for row in actual.values():
        groups[row["dataset"],row["source"],row["target"]].append(row)
    directions={}
    for source in languages:
        for target in languages:
            if source==target:
                continue
            conversational={d:summarize(groups[d,source,target],cases) for d in CONVERSATION_DATASETS}
            measured=[v for v in conversational.values() if v["messages"]]
            directions[source+"-"+target]=dict(
                conversation_status="measured_diagnostic" if measured else "unmeasured",
                availability_floor_met_in_sampled_datasets=bool(measured) and all(v["availability_floor_met"] for v in measured),
                conversation_datasets=conversational,
                reference_datasets={d:summarize(groups[d,source,target],cases) for d in REFERENCE_DATASETS})
    missing=[p for p,v in directions.items() if v["conversation_status"]=="unmeasured"]
    passed=[p for p,v in directions.items() if v["availability_floor_met_in_sampled_datasets"]]
    return dict(
        schema="vipi-immersion-coverage-scorecard-1",platform=validation["platform"],
        fixture_manifest_sha256=sha(fixture/"manifest.json"),native_report_sha256=sha(report_path),
        denominator_policy="Every input message in each named dataset; identifier failures, no-word messages and abstentions remain included. No selector-dependent exclusions.",
        protocol=dict(availability_target=.9,semantic_accuracy_target=.99,
            depth_levels=list(DEPTH_LEVELS),depth_acceptance_threshold=None,
            depth_interpretation="Maximum selected spans at density=1. Touched words include partial lexical carriers; fully covered words are separate. These are headroom diagnostics, not live density-setting tests.",
            population_claim="None: reused native translations, task/persona/SMS/speech samples and reference diagnostics are not a representative population survey.",
            reference_caution="FLORES translations share underlying sentences across directions; reference scores never replace missing conversational evidence.",
            semantic_accuracy="Unknown: passing authored regressions is not independent semantic acceptance.",
            learning_outcome="Unmeasured: coverage and accuracy do not establish intermediate fluency."),
        native_regressions_passed=validation["passed"],
        direction_count=len(directions),conversational_directions_measured=len(directions)-len(missing),
        conversational_directions_missing=missing,
        directions_meeting_availability_floor_in_sampled_datasets=passed,
        all_directions_meet_availability_floor=not missing and len(passed)==len(directions),
        independent_semantic_acceptance=False,useful_immersion_target_demonstrated=False,
        directions=directions)

def main(a):
    value=scorecard(a.fixture,a.report)
    with a.output.open("x") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print(json.dumps({k:v for k,v in value.items() if k not in {"directions","protocol"}},ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("fixture","report","output"):
        p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())

