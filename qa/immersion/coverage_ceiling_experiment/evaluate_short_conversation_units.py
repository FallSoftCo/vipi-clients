#!/usr/bin/env python3
"""Bounded research: complete short units, unchanged starter guards, explicit budget."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time
import unicodedata

from evaluate_source_concepts import candidates as word_candidates
from evaluate_reviewed_words import WORD, PROTECTED, u16


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def key(s):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC',s).replace('’',"'")).casefold().strip()


def same_face(a,b):
    return ''.join(c for c in key(a) if c.isalnum()) == ''.join(c for c in key(b) if c.isalnum())


def complete_units(text, target_data):
    entries={r['source']:r for r in target_data['rows'] if r['target']}
    found=[];rejected=[];cursor=0
    # Boundaries cannot split a complement on a comma or an arbitrary token window.
    boundaries=[m.end() for m in re.finditer(r'[.!?]+(?=\s|$)',text)]
    if not boundaries or boundaries[-1]!=len(text):boundaries.append(len(text))
    protected=list(PROTECTED.finditer(text))
    for end in boundaries:
        start=cursor;cursor=end
        while start<end and text[start].isspace():start+=1
        while end>start and text[end-1].isspace():end-=1
        original=text[start:end]
        if not original:continue
        suffix=re.search(r'[.!?]+$',original)
        punctuation=suffix.group() if suffix else ''
        body=original[:suffix.start()] if suffix else original
        unit=entries.get(key(body))
        if not unit:continue
        reason=None
        if '"' in text or '“' in text or '”' in text or '`' in text:
            reason='quoted_or_code_message'
        elif '..' in punctuation or (start and text[:start].rstrip().endswith('...')):
            reason='ellipsis_incomplete_scope'
        elif re.search(r'\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc)\.\s*$',text[:start],re.I):
            reason='abbreviation_boundary_uncertain'
        elif any(m.start()<end and start<m.end() for m in protected):
            reason='protected_literal'
        elif unit['require_question_mark'] and '?' not in punctuation:
            reason='question_mark_required'
        elif unit['reject_question_mark'] and '?' in punctuation:
            reason='statement_target_question_source'
        elif same_face(original,unit['target']):
            reason='unchanged_face'
        words=list(WORD.finditer(original))
        anchor_words=[w for w in words if key(w.group()) in unit['content_anchors']]
        span=dict(start=start,end=end,sourceStartUTF16=u16(text[:start]),sourceEndUTF16=u16(text[:end]),
            original=original,translated=unit['target'],reading=unit['reading'],category=unit['category'],
            lexicon_id=unit['id'],train_rank=unit['train_rank'],changed_source_words=len(words),
            content_source_words=len(anchor_words),source_kind='complete_short_unit',
            whole_message=not text[:start].strip() and not text[end:].strip())
        (rejected if reason else found).append(dict(span,reason=reason) if reason else span)
    return found,rejected


def starter_candidates(text, pack, target):
    entries=pack['pairs']['en-'+target]['entries'];by_source={e['source']:e for e in entries}
    words=[e for e in entries if e.get('guard')!='interrogative']
    questions={e['source']:dict(target=e['target'],following=e['following']) for e in entries if e.get('guard')=='interrogative'}
    rules={'single_words':{k:v for k,v in questions.items() if ' ' not in k},'units':{k:v for k,v in questions.items() if ' ' in k}}
    tokens,found,rejected=word_candidates(text,{'entries':words},rules)
    for s in found:
        e=by_source[key(s['original'])]
        s.update(reading=e.get('reading'),lexicon_id=e['id'],train_rank=e['train_rank'],source_kind='reviewed_starter',content_source_words=s['changed_source_words'] if s['category']=='content' else 0)
    return tokens,found,rejected


def select(text,tokens,eligible,known='none'):
    filtered=[];rejected=[];budget=max(1,math.floor(len(tokens)*0.10))
    for s in eligible:
        reason=None
        if known=='i_and_but' and key(s['original'].strip('.!?')) in {'i','and','but'}:reason='simulated_known_face'
        elif known=='all_function' and s['category']=='function':reason='simulated_known_function_unit'
        elif s['changed_source_words']>budget:reason='native_budget_proxy_exceeded'
        if reason:rejected.append(dict(s,reason=reason))
        else:filtered.append(s)
    filtered.sort(key=lambda s:(s['category']!='content',s['train_rank'],-s['changed_source_words'],s['start'],s['lexicon_id']))
    chosen=filtered[:1]
    output=text
    if chosen:
        s=chosen[0];output=text[:s['start']]+s['translated']+text[s['end']:]
    n=len(tokens)
    return dict(spans=chosen,mixed_text=output,native_budget_proxy=budget,
        changed_depth=sum(s['changed_source_words'] for s in chosen)/n if n else 0,
        content_anchor_depth=sum(s['content_source_words'] for s in chosen)/n if n else 0,
        rejected=rejected)


def evaluate(case,pack,targets):
    text=case['text'];out={}
    for lang,data in targets.items():
        tokens,words,word_rejections=starter_candidates(text,pack,lang)
        units,rejections=complete_units(text,data)
        out[lang]=dict(source_words=len(tokens),whole_reference_units=[s for s in units if s['whole_message']],
            embedded_reference_units=[s for s in units if not s['whole_message']],
            reference_rejections=rejections,starter_rejections=word_rejections,
            arms={f'{arm}_{known}':select(text,tokens,words+(units if arm=='starter_plus_units' else []),known)
                for arm in ['starter','starter_plus_units'] for known in ['none','i_and_but','all_function']})
    return dict(case,targets=out)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();q=Path(__file__).resolve().parent;f=json.loads(a.freeze.read_text())
    for name,digest in f['files'].items():assert sha(q/name)==digest,(name,'frozen source changed')
    pack=json.loads((q/'reviewed-source-unit-native-candidate-r03.json').read_text())
    targets={l:json.loads((q/f'short-conversation-targets-en-{l}-r02.json').read_text()) for l in ['sw','ja','es']}
    protocol=json.loads(a.protocol.read_text());assert protocol['freeze_sha256']==sha(a.freeze)
    started=time.perf_counter();rows=[evaluate(c,pack,targets) for c in protocol['cases']]
    result=dict(production=False,semantic_review='pending',calls_to_any_translation_provider=0,
        current_native_runtime_control_included=False,
        boundary_source='Python English Unicode approximation, not a new native qualification',
        input_protocol_sha256=sha(a.protocol),freeze_sha256=sha(a.freeze),elapsed_ms=(time.perf_counter()-started)*1000,
        limitations=['Raw presence is not meaning approval.','Source-only starter projection is not the unchanged full native pipeline.','Whole-reference availability is not an automatic face.','Known-word simulations are not a shipped progression feature.'],rows=rows)
    assert not a.output.exists();a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(sha(a.output))


if __name__=='__main__':main()
