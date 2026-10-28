#!/usr/bin/env python3
"""Recompile changed languages and retain pinned lexical data for other languages.

A new release identity covers the whole collection. Changed sense/term relations
require fresh context mining for affected directions; this tool does not rebind
old witnesses or claim semantic acceptance.
"""
import argparse,hashlib,json,shutil,sqlite3,time
from pathlib import Path
from build_lexical_shards import compile_language,canonical,digest_file
import build_lexical_shards,native_lemma_links,noun_carriers

def main(a):
    base=json.loads(a.base.read_text())
    inventory=json.loads((a.inventory.parent/'receipt.json').read_text())
    redirects=json.loads((a.redirects.parent/'receipt.json').read_text())
    glosses=json.loads((a.gloss_links.parent/'receipt.json').read_text())
    assert inventory['complete_source_scan'] and inventory['sha256']==base['inventory_sha256']
    assert redirects['upstream_sha256']==inventory['upstream_sha256']
    assert glosses['source_inventory_sha256']==inventory['sha256']
    assert digest_file(a.redirects)==redirects['sha256'] and digest_file(a.gloss_links)==glosses['sha256']
    languages={s['language'] for s in base['shards']}
    selected=set(a.language)
    assert selected and selected<=languages
    # The immutable source inventory was already verified by the base build.
    # Compare its retained source identity in every shard before reading it.
    fingerprints={name:digest_file(Path(module.__file__)) for name,module in
        [('compiler',build_lexical_shards),('linker',native_lemma_links),('noun_carriers',noun_carriers)]}
    release=hashlib.sha256(canonical(dict(base=base['release_id'],languages=sorted(selected),
        source=inventory['sha256'],redirects=redirects['sha256'],glosses=glosses['sha256'],
        code=fingerprints,incremental_compiler=digest_file(Path(__file__)))).encode()).hexdigest()
    a.output.mkdir(parents=True,exist_ok=False)
    source_copy=a.output/'compiler-source';source_copy.mkdir()
    for file in Path(__file__).parent.glob('*.py'):shutil.copy2(file,source_copy/file.name)
    results=[]
    # Rebuild changed languages first; a failure does not duplicate the rest.
    rows=sorted(base['shards'],key=lambda x:(x['language'] not in selected,x['language']))
    for row in rows:
        language=row['language'];old=a.base.parent/(language+'.sqlite')
        assert old.stat().st_size==row['bytes'] and digest_file(old)==row['sha256']
        with sqlite3.connect(old.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            meta={k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}
        assert meta['source_inventory_sha256']==inventory['sha256']
        assert meta['redirects_sha256']==redirects['sha256']
        assert meta['native_gloss_links_sha256']==glosses['sha256']
        if language in selected:
            result=compile_language(a.inventory,a.output,language,inventory,a.redirects,redirects,
                a.gloss_links,glosses,release)
            result['recompiled']=True
        else:
            new=a.output/old.name;shutil.copyfile(old,new)
            with sqlite3.connect(new) as db:
                db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('release_id',canonical(release)))
                db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('unchanged_lexical_base_release',canonical(base['release_id'])))
                db.commit()
                assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            result=dict(row,sha256=digest_file(new),bytes=new.stat().st_size,recompiled=False)
        results.append(result)
        (a.output/'progress.json').write_text(json.dumps(dict(complete=False,shards=results),indent=2)+'\n')
        print(canonical(dict(stage='language',language=language,recompiled=result['recompiled'],bytes=result['bytes'])),flush=True)
    summary=dict(base,release_id=release,base_release_id=base['release_id'],policy=build_lexical_shards.POLICY,
        changed_languages=sorted(selected),shards=sorted(results,key=lambda x:x['language']),
        total_bytes=sum(s['bytes'] for s in results),compiler_sha256=fingerprints['compiler'],
        linker_sha256=fingerprints['linker'],incremental_compiler_sha256=digest_file(Path(__file__)),
        runtime_qualified=False,release_ready=False,
        mutation_scope='Selected languages fully recompiled from pinned evidence; other lexical rows unchanged, metadata rebound. Fresh context mining required for all affected directions.')
    (a.output/'catalog.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (a.output/'ATTRIBUTION.txt').write_text((a.base.parent/'ATTRIBUTION.txt').read_text()+
        '\nChanges: '+a.change_note+'\n')
    (a.output/'progress.json').unlink()
    print(canonical(dict(complete=True,release_id=release,bytes=summary['total_bytes'],changed_languages=sorted(selected))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['base','inventory','redirects','gloss-links','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--language',action='append',required=True)
    p.add_argument('--change-note',default='Selected languages recompiled from retained published dictionary evidence. Native identities, readings and source attribution retained.')
    main(p.parse_args())
