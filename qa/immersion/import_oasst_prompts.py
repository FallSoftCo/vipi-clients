#!/usr/bin/env python3
"""Pin human-written multilingual prompts for development replay, not training.

These are public assistant-style conversations, not representative friend chat.
No correctness, independence, or population coverage claim is made.
"""
import argparse,gzip,hashlib,json,urllib.request,shutil
from collections import Counter,defaultdict
from pathlib import Path
import unicodedata

REVISION='fdf72ae0827c1cda404aff25b6603abec9e3399b'
SOURCE='2023-04-12_oasst_prompts.messages.jsonl.gz'
PINS={SOURCE:('sha256','621ccd86a6ef320ca4e24c137121bd4b39bcc7a0df839f0897fcc965ef2076ed',12783960),
    'LICENSE':('git-sha1','261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64',11357),
    'README.md':('git-sha1','7973fcd39f6489029d0b5e7409f0ed9e6cee468a',10168)}
LANGUAGES={'en','es','fr','de','it','pt','ar','zh','ja','ko','sw'}
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(a):
    a.output.mkdir(parents=True,exist_ok=False);inputs=[]
    for name,(algorithm,expected,size) in PINS.items():
        url=f'https://huggingface.co/datasets/OpenAssistant/oasst1/resolve/{REVISION}/{name}'
        path=a.output/name;temporary=path.with_suffix(path.suffix+'.part')
        if a.inputs:
            source=a.inputs/name
            assert source.is_file() and not source.is_symlink()
            shutil.copyfile(source,temporary);count=temporary.stat().st_size
        else:
            with urllib.request.urlopen(url,timeout=60) as response,temporary.open('xb') as output:
                count=0
                while chunk:=response.read(65536):
                    count+=len(chunk);assert count<=size;output.write(chunk)
        assert count==size
        if algorithm=='sha256':actual=sha(temporary)
        else:actual=hashlib.sha1(f'blob {size}\0'.encode()+temporary.read_bytes()).hexdigest()
        assert actual==expected,(name,actual)
        temporary.rename(path);inputs.append(dict(file=name,url=url,bytes=size,sha256=sha(path)))
    counts=Counter();eligible=defaultdict(list);seen=set()
    with gzip.open(a.output/SOURCE,'rt',encoding='utf8') as f:
        for line in f:
            row=json.loads(line);counts['source_rows']+=1
            language={'pt-BR':'pt'}.get(row['lang'],row['lang'])
            if language not in LANGUAGES:continue
            counts['supported_language_rows']+=1
            if row.get('deleted') is not False or row.get('review_result') is not True or row.get('synthetic') is not False:
                counts['review_or_authorship_excluded']+=1;continue
            if row.get('role')!='prompter' or row.get('parent_id') is not None:
                counts['not_initial_human_prompt']+=1;continue
            text=row['text'];length=len(text.encode('utf-16-le'))//2
            if not 8<=length<=280 or text.count('\n')>3 or chr(96)*3 in text or not any(c.isalpha() for c in text):
                counts['outside_short_message_scope']+=1;continue
            key=(language,unicodedata.normalize('NFC',text).strip().lower())
            if key in seen:counts['duplicate_normalized_text']+=1;continue
            seen.add(key)
            eligible[language].append(dict(id='oasst1:'+row['message_id'],source=language,original=text,
                source_message_id=row['message_id'],source_tree_id=row.get('message_tree_id') or row['message_id'],
                role='prompter',synthetic=False,review_result=True,original_language_tag=row['lang']))
    selected=[]
    for language in a.language:
        assert language in LANGUAGES
        rows=sorted(eligible[language],key=lambda r:hashlib.sha256(('vipi-human-prompts-development-1:'+r['id']).encode()).hexdigest())
        assert len(rows)>=a.per_language,(language,len(rows))
        selected+=rows[:a.per_language]
    target=a.output/'development-turns.json'
    target.write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
    result=dict(schema='vipi-human-prompts-development-1',source='OpenAssistant/oasst1',
        source_revision=REVISION,inputs=inputs,license='Apache-2.0',counts=dict(counts),
        eligible_by_language={k:len(v) for k,v in sorted(eligible.items())},
        selection_languages=a.language,selected_source_turns=len(selected),language_tag_mapping={'pt-BR':'pt'},
        selection='Fixed salted SHA-256 order by original human source message identity; short positively reviewed non-synthetic initial prompts.',
        turns_sha256=sha(target),compiler_sha256=sha(Path(__file__)),complete=True,
        evaluation_scope='development-only',translation_generated=False,mapping_training_input=False,
        independent_semantic_acceptance=False,coverage_denominator_eligible=False,
        limits=['Assistant-style public prompts, not a representative sample of private friend chat.',
            'No whole-message translation or substitution has been accepted yet.',
            'Swahili is absent from this source; retain separate original Swahili evaluations.'])
    (a.output/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (a.output/'ATTRIBUTION.txt').write_text('OpenAssistant Conversations (OASST1), OpenAssistant contributors, Apache License 2.0.\nhttps://huggingface.co/datasets/OpenAssistant/oasst1\nhttps://arxiv.org/abs/2304.07327\nChanges: deterministic short-message development selection; original text and source identities retained.\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inputs',type=Path);p.add_argument('--language',action='append',required=True);p.add_argument('--per-language',type=int,default=8)
    a=p.parse_args();assert 1<=a.per_language<=100;run(a)
