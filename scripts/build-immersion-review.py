#!/usr/bin/env python3
"""Package existing native captures; never generate substitute app screenshots."""
import argparse
import json
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--android", type=Path, required=True)
parser.add_argument("--ios", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
reports = {}
for platform, source in [("android", args.android), ("ios", args.ios)]:
    report = json.loads((source / "report.json").read_text())
    rows = report["directions"]
    assert len(rows) == 90 and len({(r["source"], r["target"]) for r in rows}) == 90
    assert min(r["selected"] for r in rows) >= 2
    destination = args.output / platform
    destination.mkdir(exist_ok=True)
    phases = ["target", "meaning", "script"]
    for row in rows:
        for phase in phases:
            name = f'{row["source"]}-{row["target"]}-{phase}.png'
            assert (source / name).stat().st_size > 100
            shutil.copy2(source / name, destination / name)
    shutil.copy2(source / "report.json", destination / "report.json")
    reports[platform] = report

html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vipi · Native reading review</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif;background:#f8f7f2;color:#18251d}
*{box-sizing:border-box}body{max-width:900px;margin:auto;padding:24px}h1{font-size:clamp(28px,6vw,44px);letter-spacing:-.04em;margin-bottom:12px}p{line-height:1.6;max-width:70ch}.eyebrow{color:#32634d;font-weight:650}label{display:grid;gap:8px;font-size:14px}select,button,a{font:inherit}select,button{padding:12px;border:1px solid #b8c7bb;border-radius:12px;background:#fff;color:#18251d}button{cursor:pointer}.controls{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}#capture{display:block;width:100%;height:auto;border-radius:12px;background:white}.capture{padding:20px;background:white;border-radius:24px;min-height:160px}#phase{margin:16px 0;display:flex;gap:10px;flex-wrap:wrap}button[aria-pressed=true]{background:#32634d;color:white}#evidence{font-size:14px;color:#536357}a{color:#32634d}details{margin-top:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}@media(max-width:520px){body{padding:18px}.controls{grid-template-columns:1fr}.capture{padding:10px}}@media(prefers-color-scheme:dark){:root{background:#17211c;color:#f5f4ed}.eyebrow,a{color:#b9d9c0}#evidence{color:#c2cfc4}}
</style>
<p class="eyebrow">VIPI · INTERNAL NATIVE QA</p><h1>One thought. Two languages.</h1>
<p>Inspect the same authored conversation in all 90 directions. These are captures of the actual Android and iOS paragraph renderers, using native word segmentation. They demonstrate layout and readable vocabulary; they do not establish live translation accuracy or learning effectiveness.</p>
<div class="controls"><label>Platform<select id="platform"><option value="android">Android</option><option value="ios">iOS</option></select></label><label>Familiar language<select id="source"></select></label><label>Immersion language<select id="target"></select></label></div>
<div id="phase"><button data-phase="target" aria-pressed="true">Immersion</button><button data-phase="meaning" aria-pressed="false">Familiar meanings</button><button data-phase="script" aria-pressed="false">Original script</button><button id="play" aria-pressed="false">Start continuous preview</button></div>
<div class="capture"><img id="capture" alt=""></div><p id="evidence" aria-live="polite"></p>
<p>The preview switches captured phases every 4.5 / 3 seconds. Native app recordings in the gallery separately demonstrate the actual running clock. Both platforms include original-script component captures and expose script through the reading menu. Arabic, Chinese, Japanese and Korean immersion use authored Latin readings by default.</p>
<details><summary>Measurements and limits</summary><p>Each direction was measured at three widths and three text sizes. Each lightly rounded vocabulary block reserves its largest form. Native checks compare all glyph positions across phases, so surrounding text stays still. These examples cover coffee, tomorrow and river. General dictionary packs, context-sensitive readings, actual translation quality and real chat behavior remain separate acceptance gates.</p><pre id="measurements"></pre></details>
<p><a href="android/report.json">Android evidence</a> · <a href="ios/report.json">iOS evidence</a></p>
<script>
const reports=__REPORTS__;
const languages={en:'English',es:'Spanish',fr:'French',de:'German',it:'Italian',pt:'Portuguese',ar:'Arabic',zh:'Chinese',ja:'Japanese',ko:'Korean'};
const platform=document.querySelector('#platform'),source=document.querySelector('#source'),target=document.querySelector('#target'),capture=document.querySelector('#capture'),play=document.querySelector('#play');
for(const input of [source,target])for(const [code,name] of Object.entries(languages)){const option=document.createElement('option');option.value=code;option.textContent=name;input.append(option)}
source.value='en';target.value='ja';let phase='target',timer=null,running=false;
function schedule(){clearTimeout(timer);if(running&&!document.hidden)timer=setTimeout(()=>{phase=phase==='target'?'meaning':'target';render()},phase==='meaning'?3000:4500)}
function render(){if(source.value===target.value)target.value=Object.keys(languages).find(code=>code!==source.value);
 const row=reports[platform.value].directions.find(r=>r.source===source.value&&r.target===target.value);
 capture.src=`${platform.value}/${source.value}-${target.value}-${phase}.png`;capture.alt=`Native ${platform.value} paragraph: ${languages[source.value]} to ${languages[target.value]}, ${phase}`;
 document.querySelectorAll('[data-phase]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.phase===phase))});
 document.querySelector('#evidence').textContent=`${languages[source.value]} → ${languages[target.value]} · ${row.selected} authored vocabulary spans · ${row.measurements.length} size combinations`;
 document.querySelector('#measurements').textContent=JSON.stringify(row,null,2);schedule();}
for(const input of [platform,source,target])input.onchange=render;
document.querySelectorAll('[data-phase]').forEach(b=>b.onclick=()=>{phase=b.dataset.phase;render()});
play.onclick=()=>{running=!running;play.textContent=running?'Pause preview':'Start continuous preview';play.setAttribute('aria-pressed',String(running));schedule()};
document.addEventListener('visibilitychange',schedule);render();
</script></html>'''
(args.output / "review.html").write_text(html.replace("__REPORTS__", json.dumps(reports, ensure_ascii=False).replace("<", "\\u003c")))
print(json.dumps({"output": str(args.output), "directions_per_platform": 90, "captures": 540}))
