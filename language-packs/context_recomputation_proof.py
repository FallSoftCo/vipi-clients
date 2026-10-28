#!/usr/bin/env python3
"""Verify complete changed-language recomputation against pinned source corpora.

Each affected pair retains its own historical context lineage. A cumulative
release can contain several revisions of the same corpus, but a fresh pair
replacement must process every corpus with unchanged exclusion and quality rules.
"""
import json
from collections import defaultdict
from bundle_lexical_data import compatible
from build_wiktextract import digest_file

def context_ids(metadata):
    return {metadata['source_contexts_sha256'], *metadata.get('additional_contexts_sha256', [])}

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
    pair_contexts={}
    for pair in requested:
        revision=base.get('pair_context_revisions',{}).get(pair)
        pair_contexts[pair]=({revision['primary'],*revision['additional']} if revision else context_ids(base))
    expected_old=set().union(*pair_contexts.values())
    historical_proofs=[]
    receipts={json.loads(p.read_text())['sha256']:(p,json.loads(p.read_text())) for p in args.base_pair_receipt}
    if base.get('pair_context_revisions') or not base.get('disjoint_source_proof'):
        # Resolve each exact witness revision, not a stale global proof carried
        # forward from an earlier dictionary release.
        for pair in sorted(requested):
            revision=base['pair_input_revisions'][pair]
            path,row=receipts[revision]
            assert row['complete'] and pair in row['requested_pairs']
            assert context_ids(row)==pair_contexts[pair], 'Pair receipt disagrees with retained context lineage'
            assert row['disjoint_source_proof']
            historical_proofs.append(row['disjoint_source_proof'])
    else:
        historical_proofs.append(base['disjoint_source_proof'])
    for proof in historical_proofs:
        for key in ['exclusions_sha256','base_supplement_receipts','policy']:
            assert proof[key]==delta['disjoint_source_proof'][key], 'Changed source exclusion: '+key

    def contexts(paths,expected,fresh):
        rows=[json.loads(p.read_text()) for p in paths]
        assert len(rows)==len(expected) and {r['sha256'] for r in rows}==expected
        by_hash={};by_corpus=defaultdict(list)
        for path,row in zip(paths,rows):
            assert row['complete'] and not row['pilot']
            assert row['corpus_partition']=='development' and not row['reserved_sentence_text_read']
            assert row['direct_links_only'] and not row['independent_semantic_acceptance']
            if fresh:
                assert row['source_release_id']==after['release_id']
                assert row['source_catalog_sha256']==digest_file(args.dictionary_catalog)
                assert set(row['changed_pair_languages'])==changed
                assert not by_corpus[row['corpus_sha256']], 'Ambiguous replacement corpus revision'
            by_hash[row['sha256']]=(path,row)
            by_corpus[row['corpus_sha256']].append((path,row))
        return by_hash,by_corpus
    old_hash,old=contexts(args.base_context_receipt,expected_old,False)
    new_hash,new=contexts(args.replacement_context_receipt,context_ids(delta),True)
    assert old.keys()==new.keys(), 'A source corpus was dropped or added'
    for pair,identities in pair_contexts.items():
        corpus_ids=[old_hash[sha][1]['corpus_sha256'] for sha in identities]
        assert len(corpus_ids)==len(set(corpus_ids)), 'Ambiguous historical corpus within a pair'
        assert set(corpus_ids)==set(new), 'A pair source corpus was dropped or added'
    sources=[]
    for corpus in sorted(old):
        np,two=new[corpus][0]
        for op,one in sorted(old[corpus],key=lambda value:value[1]['sha256']):
            for key,default in [('corpus_receipt_sha256',None),('corpus_schema','vipi-conversation-reference-1'),
                ('automatic_sentence_alignment',False),('supplemental_receipts',[])]:
                assert one.get(key,default)==two.get(key,default), 'Changed corpus provenance: '+key
            sources.append(dict(corpus_sha256=corpus,old_context_sha256=one['sha256'],
                new_context_sha256=two['sha256'],old_receipt_sha256=digest_file(op),new_receipt_sha256=digest_file(np),
                affected_pairs=sorted(pair for pair,ids in pair_contexts.items() if one['sha256'] in ids)))
    stable=languages-changed
    filtered_before=dict(before,shards=[r for r in before['shards'] if r['language'] in stable])
    filtered_after=dict(after,shards=[r for r in after['shards'] if r['language'] in stable])
    compatible(filtered_before,filtered_after,args.dictionary_baseline.parent,
        args.dictionary_catalog.parent,output/'unchanged-pair-dictionary-proof.json')
    result=dict(schema='vipi-changed-language-context-recomputation-1',complete=True,
        baseline_catalog_sha256=digest_file(args.dictionary_baseline),
        candidate_catalog_sha256=digest_file(args.dictionary_catalog),
        base_release=before['release_id'],candidate_release=after['release_id'],
        changed_languages=sorted(changed),replaced_pairs=sorted(requested),
        historical_unchanged_pairs=sorted(f'{a}-{b}' for a in stable for b in stable if a!=b),
        unchanged_dictionary_proof_sha256=digest_file(output/'unchanged-pair-dictionary-proof.json'),
        context_sources=sources,pair_context_lineage={p:sorted(ids) for p,ids in sorted(pair_contexts.items())},
        base_pair_receipts=[dict(path=str(p),sha256=digest_file(p)) for p in args.base_pair_receipt],semantic_accuracy_claim=False,
        policy='Complete affected pair replacement from the same pinned corpora; other pairs retain historical witness counts and original mining provenance.')
    path=output/'recomputation-proof.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result,digest_file(path)
