#!/usr/bin/env python3
"""Verify complete changed-language recomputation against pinned source corpora.

Unchanged pairs keep their historical lexical evidence and explicit lineage.
Changed pairs must be recomputed, including empty results, from every prior
corpus with unchanged reserved-text exclusion and quality policies.
"""
import json
from pathlib import Path
from bundle_lexical_data import compatible
from build_wiktextract import digest_file

def verify_recomputation(args,base,delta,output):
    before=json.loads(args.dictionary_baseline.read_text())
    after=json.loads(args.dictionary_catalog.read_text())
    assert base['source_release_id']==before['release_id']
    assert delta['source_release_id']==after['release_id']
    old_languages={s['language'] for s in before['shards']}
    languages={s['language'] for s in after['shards']}
    changed=set(after['changed_languages'])
    assert languages==old_languages and changed and changed<languages
    requested={f'{a}-{b}' for a in languages for b in languages if a!=b and (a in changed or b in changed)}
    assert requested==set(delta['requested_pairs']), 'Every affected direction must be replaced, including empty results'
    assert delta['disjoint_source_proof']
    historical_proofs=[]
    if base.get('disjoint_source_proof'):
        historical_proofs.append(base['disjoint_source_proof'])
    else:
        # Older cumulative replacements retained per-pair revision hashes but
        # not a global proof. Resolve the exact affected revision receipts.
        receipts={json.loads(p.read_text())['sha256']:(p,json.loads(p.read_text()))
            for p in args.base_pair_receipt}
        for pair in requested:
            revision=base['pair_input_revisions'][pair]
            path,row=receipts[revision]
            assert row['complete'] and pair in row['requested_pairs']
            assert row['source_release_id']==base['source_release_id']
            assert row['source_contexts_sha256']==base['source_contexts_sha256']
            assert set(row['additional_contexts_sha256'])==set(base['additional_contexts_sha256'])
            historical_proofs.append(row['disjoint_source_proof'])
    for proof in historical_proofs:
        for key in ['exclusions_sha256','base_supplement_receipts','policy']:
            assert proof[key]==delta['disjoint_source_proof'][key], 'Changed source exclusion: '+key

    def contexts(paths,metadata,fresh):
        expected={metadata['source_contexts_sha256'],*metadata.get('additional_contexts_sha256',[])}
        rows=[json.loads(p.read_text()) for p in paths]
        assert len(rows)==len(expected) and {r['sha256'] for r in rows}==expected
        by_corpus={}
        for path,row in zip(paths,rows):
            assert row['complete'] and not row['pilot']
            assert row['corpus_partition']=='development' and not row['reserved_sentence_text_read']
            assert row['direct_links_only'] and not row['independent_semantic_acceptance']
            assert row['corpus_sha256'] not in by_corpus, 'Ambiguous input corpus revision'
            if fresh:
                assert row['source_release_id']==after['release_id']
                assert row['source_catalog_sha256']==digest_file(args.dictionary_catalog)
                assert set(row['changed_pair_languages'])==changed
            # Receipt identities are anchored to the checked witness database;
            # the context compiler already verified their SQLite content.
            by_corpus[row['corpus_sha256']]=(path,row)
        return by_corpus
    old=contexts(args.base_context_receipt,base,False)
    new=contexts(args.replacement_context_receipt,delta,True)
    assert old.keys()==new.keys(), 'A source corpus was dropped or added'
    sources=[]
    for corpus in sorted(old):
        op,one=old[corpus];np,two=new[corpus]
        for key,default in [('corpus_receipt_sha256',None),('corpus_schema','vipi-conversation-reference-1'),
            ('automatic_sentence_alignment',False),('supplemental_receipts',[])]:
            assert one.get(key,default)==two.get(key,default), 'Changed corpus provenance: '+key
        sources.append(dict(corpus_sha256=corpus,old_context_sha256=one['sha256'],
            new_context_sha256=two['sha256'],old_receipt_sha256=digest_file(op),new_receipt_sha256=digest_file(np)))

    # Compare the actual remaining dictionaries, not merely catalog flags.
    # Historical witness counts remain historical: extra target eligibility
    # is not represented as freshly mined context evidence.
    stable=languages-changed
    filtered_before=dict(before,shards=[r for r in before['shards'] if r['language'] in stable])
    filtered_after=dict(after,shards=[r for r in after['shards'] if r['language'] in stable])
    lexical=compatible(filtered_before,filtered_after,args.dictionary_baseline.parent,
        args.dictionary_catalog.parent,output/'unchanged-pair-dictionary-proof.json')
    result=dict(schema='vipi-changed-language-context-recomputation-1',complete=True,
        baseline_catalog_sha256=digest_file(args.dictionary_baseline),
        candidate_catalog_sha256=digest_file(args.dictionary_catalog),
        base_release=before['release_id'],candidate_release=after['release_id'],
        changed_languages=sorted(changed),replaced_pairs=sorted(requested),
        historical_unchanged_pairs=sorted(f'{a}-{b}' for a in stable for b in stable if a!=b),
        unchanged_dictionary_proof_sha256=digest_file(output/'unchanged-pair-dictionary-proof.json'),
        context_sources=sources,base_pair_receipts=[dict(path=str(p),sha256=digest_file(p)) for p in args.base_pair_receipt],semantic_accuracy_claim=False,
        policy='Complete affected pair replacement from the same pinned corpora; other pairs retain historical witness counts and original mining provenance.')
    path=output/'recomputation-proof.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result,digest_file(path)
