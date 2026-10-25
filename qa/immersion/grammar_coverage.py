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
import urllib.request
from conversation_corpus import key, sha_file, write_json

SOURCES = [
    ('en','UD_English-EWT','b7711cce01cdd4f5fcc0a8199b8a50d951b16c0c','en_ewt-ud-train.conllu'),
    ('fr','UD_French-Rhapsodie','7419314a10167fd07dc46d4faedf9ab4ef027c37','fr_rhapsodie-ud-train.conllu')]
CONTENT = {'NOUN','VERB','ADJ','ADV','INTJ'}


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
                with urllib.request.urlopen(url,timeout=60) as response: data=response.read(30_000_001)
                if len(data)>30_000_000: raise ValueError('Source size bound exceeded')
                path=folder/filename;path.write_bytes(data)
                assets.append({'url':url,'file':filename,'bytes':len(data),'sha256':sha_file(path)})
            receipt={'commit':commit,'release':'r2.18','repository':repo,'license':'CC BY-SA 4.0',
                'attribution':'See retained upstream README.md and LICENSE.txt','assets':assets}
            write_json(receipt_path,receipt)
        forms=set()
        with sqlite3.connect(args.catalog.resolve().as_uri()+'?mode=ro',uri=True) as catalog:
            for text, in catalog.execute('SELECT DISTINCT source_key FROM revisions WHERE source_language=?',(language,)):
                forms.add(key(text))
        counts=Counter();vocabulary=Counter();missing=Counter();features=Counter();relations=Counter();shapes=Counter()
        for metadata,words in sentences(folder/name):
            counts['sentences']+=1;counts['syntactic_tokens']+=len(words)
            recognized=0;content=0
            by_id={word[0]:word for word in words}
            for identifier,form,lemma,pos,xpos,feats,head,relation,deps,misc in words:
                relations[relation]+=1
                if feats!='_': features.update(feats.split('|'))
                if head in by_id:
                    shapes[pos+'-'+relation+'->'+by_id[head][3]]+=1
                if pos not in CONTENT: continue
                content+=1;vocabulary[(key(lemma),pos)]+=1
                if key(form) in forms: recognized+=1
                else: missing[(key(form),key(lemma),pos)]+=1
            counts['content_tokens']+=content;counts['recognized_content_surfaces']+=recognized
            counts['sentences_with_content']+=content>0
            counts['sentences_with_any_recognized_content_surface']+=recognized>0
        records.append({'language':language,'corpus':repo,'source_receipt_sha256':sha_file(receipt_path),
            'split':'official train only','counts':dict(counts),
            'content_surface_recognition':counts['recognized_content_surfaces']/counts['content_tokens'],
            'top_content_lemmas':[{'lemma':word,'pos':pos,'count':n} for (word,pos),n in vocabulary.most_common(100)],
            'top_missing_surfaces':[{'surface':word,'lemma':lemma,'pos':pos,'count':n} for (word,lemma,pos),n in missing.most_common(100)],
            'grammar_features':dict(features.most_common()),'dependency_relations':dict(relations.most_common()),
            'dependency_shapes':dict(shapes.most_common(100))})
    write_json(args.output,{'schema':'vipi-conversation-grammar-coverage-1',
        'catalog_sha256':sha_file(args.catalog),'analyzer_sha256':sha_file(Path(__file__)),
        'languages':records,'linguistic_acceptance':False,'runtime_integration':False,
        'limits':['These two corpora do not establish ten-language conversational coverage.',
          'Source-form recognition ignores target language, correct sense, inflection, reading, and contextual eligibility.',
          'Content POS excludes pronouns, function words, names, numbers, and punctuation from the coverage denominator.',
          'Grammar distributions reflect each corpus annotation quality and genre, not every conversation.']})
    print(json.dumps([{'language':x['language'],**x['counts'],'recognition':x['content_surface_recognition']} for x in records]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','catalog','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
