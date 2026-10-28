#!/usr/bin/env python3
"""Replace complete recomputed pair scopes, including pairs with zero witnesses.

Never union successful rows from overlapping evidence. The replacement compiler
must have processed both the prior corpus and a proven disjoint additional one.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
from build_wiktextract import canonical,digest_file


def checked(path):
    receipt=json.loads((path.parent/'receipt.json').read_text())
    assert receipt['complete'] and receipt['sha256']==digest_file(path)
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
        metadata={k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}
        assert metadata['schema']=='vipi-context-witnesses-1' and not metadata['release_ready']
        assert metadata['counts']['witnesses']==db.execute('SELECT count(*) FROM witnesses').fetchone()[0]
    return receipt,metadata


def replace(args):
    base,metadata=checked(args.base);replacement,delta=checked(args.replacement)
    recomputation=None
    is_recomputation=bool(getattr(args,'dictionary_baseline',None))
    if not is_recomputation:
        assert metadata['source_release_id']==delta['source_release_id']
    for field in ['policy','minimum_support','minimum_agreement']:
        assert metadata[field]==delta[field]
    if not is_recomputation:
        assert delta['source_contexts_sha256']==metadata['source_contexts_sha256']
    assert delta['disjoint_source_proof'] and delta['additional_contexts_sha256']
    requested={tuple(value.split('-')) for value in delta['requested_pairs']}
    assert requested and all(len(pair)==2 and pair[0]!=pair[1] for pair in requested)
    assert {tuple(value.split('-')) for value in delta['pairs']}<=requested
    # A later update may not silently replace evidence from a previous corpus.
    if not is_recomputation:
        assert set(metadata.get('additional_contexts_sha256',[]))<=set(delta['additional_contexts_sha256'])
    args.output.mkdir(parents=True,exist_ok=False);path=args.output/'witnesses.sqlite'
    if is_recomputation:
        from context_recomputation_proof import verify_recomputation
        recomputation,proof_sha=verify_recomputation(args,metadata,delta,args.output)
    assert not Path(str(args.base)+'-wal').exists()
    shutil.copyfile(args.base,path)
    db=sqlite3.connect(path);db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA cache_size=-32768')
    db.execute('ATTACH DATABASE ? AS replacement',(args.replacement.resolve().as_uri()+'?mode=ro&immutable=1',))
    assert not db.execute('''SELECT 1 FROM references_used a JOIN replacement.references_used b USING(sentence)
        WHERE a.owner<>b.owner LIMIT 1''').fetchone(), 'Conflicting source identities'
    for pair in sorted(requested):
        for table in ['witnesses','evidence']:
            db.execute('DELETE FROM '+table+' WHERE source=? AND target=?',pair)
            db.execute('INSERT INTO '+table+' SELECT * FROM replacement.'+table+' WHERE source=? AND target=?',pair)
        db.commit()
    db.execute('INSERT OR IGNORE INTO references_used SELECT * FROM replacement.references_used')
    pairs={a+'-'+b:n for a,b,n in db.execute('SELECT source,target,count(*) FROM witnesses GROUP BY source,target')}
    provenance=metadata.get('pair_input_revisions',{pair:base['sha256'] for pair in metadata.get('requested_pairs',metadata['pairs'])})
    provenance.update({'-'.join(pair):replacement['sha256'] for pair in requested})
    if recomputation:
        historical_contexts={pair:dict(primary=metadata['source_contexts_sha256'],
            additional=metadata.get('additional_contexts_sha256',[])) for pair in metadata['pairs']}
        historical_contexts.update(metadata.get('pair_context_revisions',{}))
        for pair in requested:
            historical_contexts['-'.join(pair)]=dict(primary=delta['source_contexts_sha256'],
                additional=delta['additional_contexts_sha256'])
        metadata.update(source_release_id=delta['source_release_id'],
            context_evidence_dictionary_release_id=recomputation['base_release'],
            dictionary_recomputation_proof_sha256=proof_sha,
            pair_context_revisions=historical_contexts)
    metadata.update(pairs=pairs,pair_input_revisions=provenance,requested_pairs=sorted(provenance),
        counts=dict(witnesses=sum(pairs.values()),retained_reference_records=db.execute('SELECT count(*) FROM references_used').fetchone()[0]),
        additional_contexts_sha256=sorted(set(metadata.get('additional_contexts_sha256',[]))|set(delta['additional_contexts_sha256'])) if recomputation else delta['additional_contexts_sha256'],
        pair_replacement_policy='complete-pair-replacement-including-abstentions-1',
        parent_witness_sha256=base['sha256'],replacement_witness_sha256=replacement['sha256'],
        replaced_pairs=sorted('-'.join(pair) for pair in requested),
        parent_compiler_sha256=metadata['compiler_sha256'],compiler_sha256=digest_file(Path(__file__)),
        replacement_compiler_sha256=digest_file(Path(__file__)),
        license='; '.join(dict.fromkeys([metadata['license'],delta['license']])),
        automatic_sentence_alignment=metadata.get('automatic_sentence_alignment',False) or delta.get('automatic_sentence_alignment',False),
        independent_semantic_acceptance=False,release_ready=False)
    db.executemany('INSERT OR REPLACE INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()]);db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    result=dict(metadata,complete=True,sha256=digest_file(path),bytes=path.stat().st_size)
    (args.output/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (args.output/'ATTRIBUTION.txt').write_text((args.base.parent/'ATTRIBUTION.txt').read_text()+'\n'+
        (args.replacement.parent/'ATTRIBUTION.txt').read_text()+'\nComplete pair scopes replaced from cumulative evidence, including removed mappings.\n')
    print(canonical(dict(bytes=result['bytes'],sha256=result['sha256'],pairs=pairs,replaced_pairs=result['replaced_pairs'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['base','replacement','output']:parser.add_argument('--'+name,type=Path,required=True)
    for name in ['dictionary-baseline','dictionary-catalog']:
        parser.add_argument('--'+name,type=Path)
    for name in ['base-context-receipt','replacement-context-receipt','base-pair-receipt']:
        parser.add_argument('--'+name,type=Path,action='append',default=[])
    args=parser.parse_args()
    if any([args.dictionary_baseline,args.dictionary_catalog,args.base_context_receipt,args.replacement_context_receipt]):
        assert all([args.dictionary_baseline,args.dictionary_catalog,args.base_context_receipt,args.replacement_context_receipt])
    replace(args)
