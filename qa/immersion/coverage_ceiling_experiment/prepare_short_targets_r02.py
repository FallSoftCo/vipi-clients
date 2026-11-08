#!/usr/bin/env python3
"""Apply the retained pre-holdout authoring review without altering frozen drafts."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();args.output_dir.mkdir(exist_ok=False)
    q=Path(__file__).resolve().parent
    sp=q/'short-conversation-source-freeze-r01.json';sources=json.loads(sp.read_text())
    content={'agree','cool','awesome','pets','fun','great','true','live','interesting','see','know','love','hobbies','nice','kids','work','married','amazing','studying','sorry','hear','good','hope'}
    outputs={}
    for lang in ['sw','ja','es']:
        dp=q/f'short-conversation-target-draft-en-{lang}-r01.json';rp=q/f'short-conversation-target-review-root-en-{lang}-r01.json'
        draft=json.loads(dp.read_text());review=json.loads(rp.read_text())
        assert review['draft_sha256']==sha(dp)
        ds={r['source']:r for r in draft['rows']};rs={r['source']:r for r in review['rows']};rows=[]
        for s in sources['rows']:
            d=ds[s['source']];r=rs[s['source']]
            available=r['decision'].startswith('accept_') or r['decision']=='revise_target_before_freeze'
            target=r['proposed_target'] if available else None
            reading=r.get('proposed_reading',d.get('reading')) if available else None
            anchors=[w for w in s['source'].split() if w in content]
            question=s['source'].startswith(('how about ','what about ','do you ','where ','what are ','are you ')) or s['source'] in {'and you','really'}
            rows.append(dict(id=s['id']+f'-en-{lang}',source=s['source'],sense_group=s['sense_group'],
                target=target,reading=reading,status='available_for_frozen_experiment' if available else 'unavailable',
                source_tokens=s['source'].split(),content_anchors=anchors,category='content' if anchors else 'function',
                train_rank=s['source_rank'],speech_act='question' if question else 'statement_or_reaction',
                require_question_mark=s['source'] in {'and you','really'},
                reject_question_mark=not question,authored_register='Informal singular tú' if lang=='es' else 'Neutral polite with ordinary pronoun/address limitations' if lang=='ja' else 'Ordinary singular addressee, authored complete unit',
                draft_evidence_reference=dict(file=dp.name,sha256=sha(dp),source_row=s['source']),
                authoring_review_reference=dict(file=rp.name,sha256=sha(rp),source_row=s['source'],decision=r['decision'],reason=r['reason']),
                changed_from_draft=target!=d.get('target') or reading!=d.get('reading'),
                limits=d.get('notes',d.get('risks',[]))))
        d=dict(schema='vipi-complete-short-unit-targets-2',production=False,target_language=lang,
            version=f'short-conversation-research-en-{lang}-v002',source_selection_sha256=sha(sp),
            heldout_opened=False,rows=rows,
            interpretation='Authoring-stage accepted inputs for a frozen experiment, not context-validated production mappings. Unavailable targets remain explicit.',
            primary_sources=draft.get('primary_verification_references',[]),
            summary=dict(source_variants=50,available=sum(r['target'] is not None for r in rows),
                distinct_available_targets=len({r['target'] for r in rows if r['target']}),
                available_content_units=sum(bool(r['target']) and r['category']=='content' for r in rows)))
        if lang=='es':d['revision_primary_note']=dict(source='https://cvc.cervantes.es/ensenanza/biblioteca_ele/plan_curricular/niveles/05_funciones_inventario_b1-b2.htm',location='5.18 Responding to good wishes',finding='Primary search-indexed curriculum contains Eso espero as a complete response. Direct open redirects to current maintenance; no claim of a fresh direct full-page read.',use='Verifies the independently authored two-word expression, no course passage copied.')
        if lang=='sw':d['revision_primary_note']=dict(source='https://products.innovativelanguage.com/books/findaway_PDFs/Swahili/swahili_lwm_audiobook.pdf',pdf_page_zero_index=7,finding='Publisher includes hobi for hobby; corroborates existence, not common frequency or the complete authored question.',use='Factual verification only. Four deictic evaluations and four sounds constructions are withheld; no replacement invented for coverage.')
        name=f'short-conversation-targets-en-{lang}-r02.json';out=args.output_dir/name;out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');outputs[name]=sha(out)
    print(json.dumps(outputs,indent=2))


if __name__=='__main__':main()
