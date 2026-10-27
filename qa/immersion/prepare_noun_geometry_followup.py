#!/usr/bin/env python3
"""Retain the spaced-homework compound error discovered in native run 031."""
import argparse
import json
from pathlib import Path
from prepare_noun_geometry import sha

def main(a):
    manifest=json.loads((a.base/"manifest.json").read_text())
    assert sha(a.base/"cases.json")==manifest["cases_sha256"]
    cases=json.loads((a.base/"cases.json").read_text())
    matches=[r for r in cases if (r["dataset"],r["id"],r["source"],r["target"])==
             ("sms","nus-0961dd4a55e2b3f1148e4842","en","es")]
    assert len(matches)==1
    row=matches[0]
    assert "books, assignments and home works" in row["original"]
    assert "trabajos de hogar" in row["translation"]
    assert "forbidden_source" not in row and "expected_source" not in row
    row.update(forbidden_source="works",forbidden_target="trabajos",
               expected_source="books",expected_target="libros")
    manifest.update(prior_manifest_sha256=sha(a.base/"manifest.json"),compiler_sha256=sha(Path(__file__)),
        noun_geometry_followup=dict(observed_run="031",id=row["id"],source="en",target="es",
            forbidden_source="works",forbidden_target="trabajos",
            reason="The source uses spaced homework in a schoolwork list; the translation uses domestic work. Do not expose a generic work fragment inside this lexical unit.",
            reviewer="author",independent_semantic_acceptance=False))
    a.output.mkdir(parents=True,exist_ok=False)
    for shard in manifest["shards"]:
        source=a.base/(shard["language"]+".sqlite")
        assert source.stat().st_size==shard["bytes"]
        (a.output/source.name).symlink_to(source.resolve())
    for name in ("diagnostic-receipt.json","evaluation-exclusions.sqlite","EVALUATION-NOTICE.txt","LICENSE-FLORES-200.txt"):
        if (a.base/name).exists():
            (a.output/name).symlink_to((a.base/name).resolve())
    path=a.output/"cases.json"
    path.write_text(json.dumps(cases,ensure_ascii=False,separators=(",",":"))+"\n")
    manifest["cases_sha256"]=sha(path)
    (a.output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(dict(cases=len(cases),manifest_sha256=sha(a.output/"manifest.json"))))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())

