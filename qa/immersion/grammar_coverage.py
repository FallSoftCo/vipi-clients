#!/usr/bin/env python3
"""Measure content vocabulary and annotated grammar in pinned UD corpora.

Use only the official training splits for prioritization. Dev/test material is
not downloaded. Form recognition is explicitly distinct from safe immersion.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import unicodedata
import urllib.request
from conversation_corpus import key, sha_file, write_json

SOURCES = [
    ('en','UD_English-EWT','b7711cce01cdd4f5fcc0a8199b8a50d951b16c0c','en_ewt-ud-train.conllu'),
    ('fr','UD_French-Rhapsodie','7419314a10167fd07dc46d4faedf9ab4ef027c37','fr_rhapsodie-ud-train.conllu'),
    ('es','UD_Spanish-GSD','6364fa8cf5420ff7156e6b383d25936d759c68a3','es_gsd-ud-train.conllu'),
    ('de','UD_German-GSD','81d8c3612a88f5867fd089e9c0a5466ef230078b','de_gsd-ud-train.conllu'),
    ('it','UD_Italian-TWITTIRO','2546072afed14d204052f4210eee94110f4ff467','it_twittiro-ud-train.conllu'),
    ('pt','UD_Portuguese-Bosque','53bb7584bec8f6b83a27eaefe0656690df9d7773','pt_bosque-ud-train.conllu'),
    ('zh','UD_Chinese-GSD','e0d85a020182e264d6384be2a59c0f4879a1cc35','zh_gsd-ud-train.conllu'),
    ('ja','UD_Japanese-GSD','33e7310b58308e85fd2b33a2fc3ef3e434f821c7','ja_gsd-ud-train.conllu'),
    ('ko','UD_Korean-GSD','02c343e4e1e3180069f637e68a791ec6b96dd33a','ko_gsd-ud-train.conllu')]
CONTENT = {'NOUN','VERB','ADJ','ADV','INTJ'}


def pack_key(text):
    # Runtime pack keys use lower(), not the corpus split's casefold().
    # In particular German ß must not silently become ss.
    return unicodedata.normalize('NFC',text).lower()


def sentences(path):
    words=[]; metadata={}
    with path.open() as stream:
        for line in stream:
            line=line.rstrip('\n')
            if not line:
                if words: yield metadata,words
                words=[];metadata={};continue
            if line.startswith('# '):
                parts=line[2:].split(' = ',1)
                if len(parts)==2: metadata[parts[0]]=parts[1]
            else:
                parts=line.split('\t')
                if len(parts)!=10: raise ValueError('Malformed CoNLL-U')
                # Multiword surface rows and empty nodes are not additional
                # syntactic tokens. Counting them would inflate coverage.
                if parts[0].isdigit(): words.append(parts)
    if words: yield metadata,words


def main(args):
    if args.output.exists():raise ValueError('Preserve existing report')
    args.source.mkdir(parents=True,exist_ok=True)
    records=[]
    for language,repo,commit,name in SOURCES:
        folder=args.source/repo;folder.mkdir(exist_ok=True)
        receipt_path=folder/'receipt.json'
        if receipt_path.exists():
            receipt=json.loads(receipt_path.read_text())
            if receipt['commit']!=commit: raise ValueError('Source revision mismatch')
            for item in receipt['assets']:
                if sha_file(folder/item['file'])!=item['sha256']: raise ValueError('Corpus checksum mismatch')
        else:
            assets=[]
            for filename in ('LICENSE.txt','README.md',name):
                url=f'https://raw.githubusercontent.com/UniversalDependencies/{repo}/{commit}/{filename}'
                with urllib.request.urlopen(url,timeout=60) as response: data=response.read(64_000_001)
                if len(data)>64_000_000: raise ValueError('Source size bound exceeded')
                path=folder/filename;path.write_bytes(data)
                assets.append({'url':url,'file':filename,'bytes':len(data),'sha256':sha_file(path)})
            receipt={'commit':commit,'release':'r2.18','repository':repo,'license':'CC BY-SA 4.0',
                'attribution':'See retained upstream README.md and LICENSE.txt','assets':assets}
            write_json(receipt_path,receipt)
        forms=set()
        with sqlite3.connect(args.catalog.resolve().as_uri()+'?mode=ro',uri=True) as catalog:
            for text, in catalog.execute('SELECT DISTINCT source_key FROM revisions WHERE source_language=?',(language,)):
                forms.add(key(text))
        readme=(folder/'README.md').read_text()
        if 'License: CC BY-SA 4.0' not in readme:raise ValueError('Changed source license declaration')
        annotation={k:v for k,v in (line.split(': ',1) for line in readme.splitlines() if ': ' in line)
                    if k in ('Genre','Lemmas','UPOS','Features','Relations')}
        pair_forms={};pair_counts={};pack_receipts=[]
        if args.packs:
            for manifest_path in sorted(args.packs.glob(language+'-*/manifest.json')):
                manifest=json.loads(manifest_path.read_text());database=manifest_path.with_name('vocabulary.sqlite')
                if manifest['source_language']!=language or sha_file(database)!=manifest['sha256']:
                    raise ValueError('Pack identity mismatch')
                target=manifest['target_language']
                if target in pair_forms:raise ValueError('Duplicate target')
                with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
                    pair_forms[target]={row[0] for row in db.execute('SELECT DISTINCT source FROM vocabulary')}
                pair_counts[target]=Counter()
                pack_receipts.append({'target':target,'sha256':manifest['sha256'],'revision':manifest['revision']})
            if len(pair_forms)!=9:raise ValueError('Expected all nine target packs for each source')
        counts=Counter();vocabulary=Counter();missing=Counter();features=Counter();relations=Counter();shapes=Counter()
        content_by_pos=Counter();unknown_with_lemma=Counter();phenomena=Counter()
        for metadata,words in sentences(folder/name):
            counts['sentences']+=1;counts['syntactic_tokens']+=len(words)
            recognized=0;content=0
            by_id={word[0]:word for word in words}
            tags={feat for word in words for feat in word[5].split('|')}
            rels={word[7] for word in words}
            indicators={'negative_annotation':'Polarity=Neg' in tags,
                'possession_annotation':'Poss=Yes' in tags or bool(rels & {'nmod:poss','det:poss'}),
                'past_tense_annotation':'Tense=Past' in tags,
                'plural_annotation':'Number=Plur' in tags,
                'subordinate_clause':any(r.split(':')[0] in {'ccomp','xcomp','advcl','acl','csubj'} for r in rels),
                'proper_name':any(w[3]=='PROPN' for w in words),
                'question_punctuation':any(w[1] in {'?','？','؟'} for w in words)}
            phenomena.update(k for k,v in indicators.items() if v)
            sentence_pairs={target:False for target in pair_forms}
            for identifier,form,lemma,pos,xpos,feats,head,relation,deps,misc in words:
                relations[relation]+=1
                if feats!='_': features.update(feats.split('|'))
                if head in by_id:
                    shapes[pos+'-'+relation+'->'+by_id[head][3]]+=1
                if pos not in CONTENT: continue
                content+=1;vocabulary[(key(lemma),pos)]+=1
                content_by_pos[pos]+=1
                if key(form) in forms: recognized+=1
                else: missing[(key(form),key(lemma),pos)]+=1
                for target,available in pair_forms.items():
                    pair_counts[target]['content_tokens']+=1
                    # These corpora do not contain Arabic; NFC/lower matches
                    # the nine source languages' current pack normalization.
                    hit=pack_key(form) in available
                    pair_counts[target]['recognized_content_surfaces']+=hit
                    sentence_pairs[target]|=hit
                    if not hit and lemma!='_' and pack_key(lemma) in available:
                        pair_counts[target]['unrecognized_surface_with_known_lemma']+=1
                        unknown_with_lemma[(key(form),key(lemma),pos)]+=1
            counts['content_tokens']+=content;counts['recognized_content_surfaces']+=recognized
            counts['sentences_with_content']+=content>0
            counts['sentences_with_any_recognized_content_surface']+=recognized>0
            for target,hit in sentence_pairs.items():
                pair_counts[target]['sentences_with_content']+=content>0
                pair_counts[target]['sentences_with_any_recognized_content_surface']+=hit
        records.append({'language':language,'corpus':repo,'source_receipt_sha256':sha_file(receipt_path),
            'split':'official train only','annotation_metadata':annotation,'counts':dict(counts),
            'content_tokens_by_pos':dict(content_by_pos),'sentences_by_annotated_phenomenon':dict(phenomena),
            'native_pack_source_recognition':[{**r,**dict(pair_counts[r['target']])} for r in pack_receipts],
            'known_lemma_missing_surface_priorities':[{'surface':f,'lemma':l,'pos':p,'directed_token_count':n}
                for (f,l,p),n in unknown_with_lemma.most_common(100)],
            'content_surface_recognition':counts['recognized_content_surfaces']/counts['content_tokens'],
            'top_content_lemmas':[{'lemma':word,'pos':pos,'count':n} for (word,pos),n in vocabulary.most_common(100)],
            'top_missing_surfaces':[{'surface':word,'lemma':lemma,'pos':pos,'count':n} for (word,lemma,pos),n in missing.most_common(100)],
            'grammar_features':dict(features.most_common()),'dependency_relations':dict(relations.most_common()),
            'dependency_shapes':dict(shapes.most_common(100))})
    write_json(args.output,{'schema':'vipi-conversation-grammar-coverage-2',
        'catalog_sha256':sha_file(args.catalog),'analyzer_sha256':sha_file(Path(__file__)),
        'languages':records,'linguistic_acceptance':False,'runtime_integration':False,
        'limits':['Nine source languages; Arabic remains absent. Mixed genres do not establish representative conversational coverage.',
          'Source-form recognition ignores target language, correct sense, inflection, reading, and contextual eligibility.',
          'Native-pack recognition is direction-specific but still does not execute context selection or establish correct substitutions.',
          'A known lemma with an unknown surface is an inflection priority, not authority to replace a stem or change person/tense.',
          'Question punctuation is a surface indicator; other phenomenon counts depend on available annotations, not inferred semantics.',
          'Japanese and Korean feature annotations are largely absent; zero does not mean a grammar phenomenon is absent.',
          'Chinese GSD uses traditional script; do not interpret its recognition as simplified Chinese chat coverage.',
          'Italian TWITTIRO deliberately samples irony; its frequencies do not represent ordinary Italian conversation.',
          'Content POS excludes pronouns, function words, names, numbers, and punctuation from the coverage denominator.',
          'Grammar distributions reflect each corpus annotation quality and genre, not every conversation.']})
    print(json.dumps([{'language':x['language'],**x['counts'],'recognition':x['content_surface_recognition']} for x in records]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','catalog','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--packs',type=Path)
    main(p.parse_args())
