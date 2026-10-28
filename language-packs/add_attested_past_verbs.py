#!/usr/bin/env python3
"""Compile attested complete positive past verbs for English, Japanese and Korean.

Mode 4 is deliberately outside the existing reader's mode 1..3 path. A new
native matcher must establish compatible past forms, context and exact readings.
This compiler does not approve runtime integration or sentence accuracy.
"""
import argparse,hashlib,json,shutil,sqlite3,unicodedata
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path
from build_wiktextract import EXCLUDED,canonical,digest_file
from context_hints import lookup_key
POLICY='native-linked-attested-past-verbs-17'
RULE='attested-positive-past-verb-1'
READING_RULE='supplied-past-verb-reading-1'
ALLOWED={'past','indicative','formal','informal','polite','honorific','first-person','second-person','third-person','singular','plural','form-of'}
CONFLICT={'present','non-past','future','negative','passive','causative','potential','conditional','participle','infinitive','imperative','conjunctive','continuative'}
READING_SCHEMA="""CREATE TABLE surface_readings(normalized TEXT NOT NULL,lexeme INTEGER NOT NULL,
 sense TEXT NOT NULL,reading TEXT NOT NULL,source_indices TEXT NOT NULL,
 PRIMARY KEY(normalized,lexeme,sense,reading)) WITHOUT ROWID;"""
def reading_key(value):
    return unicodedata.normalize('NFC',value).replace('ʔ','ʾ').replace("'","ʾ").replace('’','ʾ').replace('ʻ','ʿ')
def acceptable(tags):
    return 'past' in tags and tags<=ALLOWED and not tags&EXCLUDED
def source_class(head,written,all_tags,language):
    usable=[set(tags) for tags in all_tags if not set(tags)&EXCLUDED]
    if written==head or any(tags&{'present','non-past','future','infinitive'} for tags in usable):
        return 'past-source-syncretic'
    if any(tags&CONFLICT for tags in usable):
        return 'past-source-requires-finite-clause' if language=='en' and all(not tags&(CONFLICT-{'participle'}) for tags in usable) else 'past-source-ambiguous'
    return 'past-source-unambiguous'
def qualify_past_tags(raw,language):
    """Recover a missing polite-past label only from two supplied complete forms."""
    if language!='ja':return raw,{}
    present=defaultdict(list)
    for index,written,reading,tags in raw:
        if set(json.loads(tags))=={'polite'} and written.endswith('ます') and reading.endswith('masu'):
            present[(written,reading)].append(index)
    output=[];proofs={}
    for index,written,reading,tags in raw:
        parsed=set(json.loads(tags))
        if parsed=={'polite'} and written.endswith('ました') and reading.endswith('mashita'):
            pair=(written[:-3]+'ます',reading[:-7]+'masu')
            indices=present.get(pair)
            if indices:
                parsed.add('past')
                proofs[index]=dict(rule='japanese-supplied-polite-past-1',paired_indices=indices,
                    paired_written=pair[0],paired_reading=pair[1],
                    reference='https://en.wiktionary.org/w/index.php?title=ました&oldid=89112196',
                    inference='Classify the supplied -mashita form as past; neither spelling nor pronunciation is generated.')
        output.append((index,written,reading,json.dumps(sorted(parsed))))
    return output,proofs

def variants(head,raw,language):
    original_tags={index:json.loads(tags) for index,_,_,tags in raw}
    raw,grammar_proofs=qualify_past_tags(raw,language)
    grouped=defaultdict(list)
    for index,written,reading,tags in raw:
        if not 1<len(written)<=64 or not written.isalpha():continue
        grouped[written].append((index,reading,set(json.loads(tags))))
    for written,rows in sorted(grouped.items()):
        accepted=[row for row in rows if acceptable(row[2])]
        if not accepted:continue
        if language!='en':
            readings={reading for _,reading,_ in accepted if reading}
            if len(readings)!=1 or any(not reading for _,reading,_ in accepted):continue
            reading=readings.pop()
            if len(reading)>96:continue
        else:reading=''
        yield dict(written=written,reading=reading,indices=sorted({i for i,_,_ in accepted}),
            features=[RULE,'past','positive','active',source_class(head,written,[tags for _,_,tags in rows],language)]+
                ([READING_RULE] if language!='en' else [])+
                (['japanese-supplied-polite-past-1'] if any(i in grammar_proofs for i,_,_ in accepted) else []),
            supplied=[dict(index=i,reading=r,tags=original_tags[i],classified_tags=sorted(t),
                grammar_proof=grammar_proofs.get(i)) for i,r,t in rows])
def build(args):
    base=json.loads(args.base.read_text());readings_receipt=json.loads(args.readings.with_name('receipt.json').read_text())
    assert readings_receipt['complete'] and digest_file(args.readings)==readings_receipt['sha256']
    assert base['inventory_sha256']==readings_receipt['inventory_sha256']==digest_file(args.inventory)
    recipe=dict(policy=POLICY,compiler_sha256=digest_file(Path(__file__)),base_catalog_sha256=digest_file(args.base),
        inventory_sha256=base['inventory_sha256'],readings_sha256=readings_receipt['sha256'])
    release=hashlib.sha256(canonical(recipe).encode()).hexdigest()
    args.output.mkdir(exist_ok=False,parents=True);shards=[];examples=[];totals={}
    with closing(sqlite3.connect(args.inventory.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as inventory,closing(sqlite3.connect(args.readings.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as readings:
        for language in ['en','ja','ko']:
            row=next(r for r in base['shards'] if r['language']==language)
            source=args.base.parent/(language+'.sqlite');assert digest_file(source)==row['sha256']
            target=args.output/source.name;shutil.copyfile(source,target);counts=Counter()
            with closing(sqlite3.connect(target)) as db:
                db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA cache_size=-16384')
                if language!='en':db.executescript(READING_SCHEMA)
                entries=db.execute("""SELECT id,headword FROM lexemes WHERE pos='verb' AND target_safe=1
                    AND EXISTS (SELECT 1 FROM terms WHERE lexeme=id AND eligible=1)""").fetchall()
                for lexeme,head in entries:
                    supplied=inventory.execute('SELECT form,tags FROM native_forms WHERE source_line=? ORDER BY form,tags',(lexeme,)).fetchall()
                    if language=='en':
                        raw=[(i,form,'',tags) for i,(form,tags) in enumerate(supplied)]
                        allowed_senses={r[0] for r in db.execute('SELECT sense FROM terms WHERE lexeme=? AND eligible=1',(lexeme,))}
                        heads=[]
                    else:
                        raw=readings.execute('SELECT form_index,form,reading,tags FROM form_readings WHERE source_line=? ORDER BY form_index',(lexeme,)).fetchall()
                        heads=sorted({reading_key(form) for form,tags in supplied if set(json.loads(tags))=={'romanization'}})
                        allowed_senses={sense for sense,reading in db.execute('SELECT sense,reading FROM terms WHERE lexeme=? AND eligible=1',(lexeme,))
                            if reading and reading_key(reading) in heads}
                    if not allowed_senses:counts['no_pronunciation_matched_meaning']+=1;continue
                    for form in variants(head,raw,language):
                        word=lookup_key(form['written'],language)
                        existing={r[0] for r in db.execute('SELECT mode FROM surfaces WHERE normalized=? AND lexeme=?',(word,lexeme))}
                        if not existing:counts['not_previously_indexed']+=1;continue
                        if language!='en' and existing&{1,2,3}:counts['existing_usable_geometry']+=1;continue
                        end=len(form['written'].encode('utf-16-le'))//2
                        db.execute('INSERT INTO surfaces VALUES (?,?,?,?,?,?,?,?)',(word,lexeme,form['written'],0,end,0,4,canonical(form['features'])))
                        evidence=dict(source_line=lexeme,headword=head,head_romanizations=heads,
                            allowed_senses=sorted(allowed_senses),forms=form['supplied'],source_indices=form['indices'],
                            source_index_kind='sorted-native-form-row' if language=='en' else 'original-wiktextract-form-index')
                        db.execute('INSERT INTO carrier_evidence VALUES (?,?,?,?)',(lexeme,form['written'],RULE,canonical(evidence)))
                        if language!='en':
                            for sense in sorted(allowed_senses):
                                db.execute('INSERT OR IGNORE INTO surface_readings VALUES (?,?,?,?,?)',(word,lexeme,sense,form['reading'],canonical(form['indices'])))
                        counts['complete_past_forms']+=1
                        if 'japanese-supplied-polite-past-1' in form['features']:counts['japanese-supplied-polite-past-1']+=1
                        counts[next(f for f in form['features'] if f.startswith('past-source-'))]+=1
                        if len(examples)<12 or head in {'go','eat','write','buy','hear','行く','食べる','書く','買う','듣다','먹다','가다','쓰다','사다'}:
                            examples.append(dict(language=language,lexeme=lexeme,headword=head,**form))
                meta=dict(policy=POLICY,release_id=release,whole_verb_schema='vipi-whole-past-verb-1',whole_verb_rule=RULE,
                    past_verb_recipe=recipe)
                if language!='en':meta.update(surface_reading_schema='vipi-surface-reading-2',surface_reading_rule=READING_RULE)
                for k,v in meta.items():db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(k,canonical(v)))
                db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                shard_counts=dict(row['counts'])
                for table in ['surfaces','carrier_evidence']:shard_counts[table]=db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                shard_counts[RULE]=counts['complete_past_forms']
            shards.append(dict(language=language,bytes=target.stat().st_size,sha256=digest_file(target),counts=shard_counts))
            totals[language]=counts;print(canonical(dict(language=language,counts=counts)),flush=True)
    catalog=dict(schema=base['schema'],policy=POLICY,release_id=release,inventory_sha256=base['inventory_sha256'],
        shards=shards,total_bytes=sum(r['bytes'] for r in shards),recipe=recipe,release_ready=False,runtime_qualified=False,
        limits=['Mode 4 requires a new native matcher. Existing stem selection remains unchanged.',
        'Only supplied complete positive active past forms; no negation, passive, causative or conditional forms.',
        'Source ambiguity and required finite-clause checks are retained explicitly. Readings are exact, sense scoped and never inferred from stems.'])
    (args.output/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    (args.output/'examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
    result=dict(complete=True,counts=totals,recipe=recipe,catalog_sha256=digest_file(args.output/'catalog.json'),
        native_qualified=False,accepted_for_context_mining=False,semantic_accuracy_claim=False)
    (args.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.output/'ATTRIBUTION.txt').write_text((args.base.parent/'ATTRIBUTION.txt').read_text()+'\n'+
        (args.readings.parent/'ATTRIBUTION.txt').read_text()+'\nExact supplied complete past verb forms; native grammar compatibility and context qualification required.\n')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['base','inventory','readings','output']:parser.add_argument('--'+name,type=Path,required=True)
    build(parser.parse_args())
