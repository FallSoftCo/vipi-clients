#!/usr/bin/env python3
"""Frozen English source policy with explicitly reviewed Japanese meanings/readings."""
import argparse
import json
from pathlib import Path
import statistics
import time
import unicodedata
from evaluate_source_concepts import evaluate, sha


def main():
    p=argparse.ArgumentParser()
    for k in ('protocol','lexicon','control','rules','freeze','output'):
        p.add_argument('--'+k,type=Path,required=True)
    args=p.parse_args();start=time.perf_counter_ns()
    protocol,lexicon,control,rules,freeze=[json.loads(getattr(args,k).read_text()) for k in ('protocol','lexicon','control','rules','freeze')]
    assert sha(args.lexicon)==protocol['lexicon_sha256']==freeze['lexicon_sha256']
    for key in ('control','rules'):
        assert sha(getattr(args,key))==freeze[key+'_sha256']
    assert sha(Path(__file__))==freeze['evaluator_sha256']
    assert sha(Path(__file__).with_name('evaluate_source_concepts.py'))==freeze['source_evaluator_sha256']
    proof={r['id']:r for r in lexicon['entries']}
    for source,rule in {**rules['single_words'],**rules['units']}.items():
        proof['question-en-ja-'+source.replace(' ','-')]=rule
    initialized=(time.perf_counter_ns()-start)/1e6;rows=[];times=[]
    for case in protocol['cases']:
        assert case['source']=='en' and case['target']=='ja'
        start=time.perf_counter_ns();row=evaluate(case,lexicon,control,rules)
        for spans in [row['candidates'],row['rejections']]+[a['spans'] for a in row['arms'].values()]:
            for span in spans:
                span['lexicon_id']=span['lexicon_id'].replace('question-en-sw-','question-en-ja-')
                exact=proof[span['lexicon_id']]
                assert span['translated']==exact['target']
                assert exact['reading'] and exact['reading_kana']
                assert all(c.isspace() or unicodedata.category(c)[0] in 'PM' or 'LATIN' in unicodedata.name(c,'') for c in exact['reading'])
                span.update(romanization=exact['reading'],reading_kana=exact['reading_kana'],reading_evidence=exact['evidence'])
        for arm in row['arms'].values():
            output,cursor='',0
            for span in arm['spans']:
                output+=case['text'][cursor:span['start']]+span['romanization'];cursor=span['end']
            arm['romanized_mixed_text']=output+case['text'][cursor:]
        times.append((time.perf_counter_ns()-start)/1e6);rows.append(row)
    output=dict(schema='vipi-japanese-source-transfer-evaluation-1',production=False,provider_calls=0,
        control_description='First100 source entries transferred to Japanese with the same target availability exclusions. Research vocabulary-size control, NOT current production runtime.',
        input_hashes={str(getattr(args,k)):sha(getattr(args,k)) for k in ('protocol','lexicon','control','rules','freeze')},
        semantic_review='pending',native_tokenizer_and_speech_qualification=False,
        timing=dict(environment='system76 existing Python CPU; not mobile',initialization_ms=initialized,median_all_arms_ms=statistics.median(times),p95_all_arms_ms=sorted(times)[int(.95*len(times))-1]),
        summaries={a:dict(messages_with_span=sum(bool(r['arms'][a]['spans']) for r in rows),mean_changed_depth=statistics.mean(r['arms'][a]['changed_depth'] for r in rows)) for a in rows[0]['arms']},rows=rows)
    assert not args.output.exists();args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(summaries=output['summaries'],timing=output['timing']),indent=2))


if __name__=='__main__':main()
