"""Copy retained full-message producer/selector observations; no inference/refit."""
import argparse, datetime, gzip, hashlib, json, os, pathlib, resource, shutil, signal, socket, time
INPUTS = {
    'trace': ('/srv/fallsoft/staging/vipi-source-name-scope-20261109-r01/outputs/project-r02/decisions.jsonl.gz', '02a8fca6cb30a0a9912658ee17d92ae2eed50d5858ce5bc7b10376d90efe9e3b'),
    'qualified': ('/srv/fallsoft/staging/vipi-context-qualified-nouns-20261109-r01/project/decisions.jsonl.gz', 'e30cd4a919fab5a97286cb384bf10c1845cc9d519bdeba1bbda908488c18a1db'),
    'geometry': ('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01/inputs/rows.jsonl', 'fc41c289c79d3d7d07a72b5f9041c359565f88cdca38deaf5cc0569530425780'),
    'family_control': ('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01/inputs/editorial-runtime-candidate-r03.json', '38a5c9989baa7603d5caf2bb03c2ca38021b56e0cba871a1b4b16e4de98aedc1'),
}
SELECTION_SHA = '59dc06af07ecbbac1786b606728972d68a9adb790edbac2687e0420ac299349d'
def sha(path):
    with open(path, 'rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('selection',type=pathlib.Path);parser.add_argument('output',type=pathlib.Path);args=parser.parse_args()
    assert socket.gethostname()=='fallsoft-production-20261106'
    started=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120 second extraction limit')));signal.alarm(120)
    assert shutil.disk_usage(args.output.parent).free >= 8*1024**3+32*1024**2
    assert sha(args.selection)==SELECTION_SHA
    assert not args.output.exists(); args.output.mkdir()
    receipt={'success':False,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'script_sha256':sha(__file__),'selection_sha256':SELECTION_SHA,'no_inference_or_refit':True}
    try:
        for path,digest in INPUTS.values():assert sha(path)==digest,path
        selection=json.loads(args.selection.read_text());wanted={r['source_id'] for r in selection['cases']};found={}
        for name in ['trace','qualified','geometry']:
            rows={};path=INPUTS[name][0]
            with (gzip.open(path,'rt') if path.endswith('.gz') else open(path)) as stream:
                for line in stream:
                    assert len(line.encode())<=4*1024**2,'Unexpected original row bound'
                    row=json.loads(line)
                    if row['id'] in wanted:
                        assert row['id'] not in rows;rows[row['id']]=row
            assert set(rows)==wanted,(name,'Missing original rows');found[name]=rows
        cases=[]
        for item in selection['cases']:
            ident=item['source_id'];t=found['trace'][ident];g=found['geometry'][ident];q=found['qualified'][ident]
            assert t['text']==g['text']==item['source']
            assert t['native_words_utf16']==g['native_source_word_ranges_utf16']==item['native_words_utf16']
            assert t['source_masks']==item['source_masks'] and t['protected_ranges_utf16']==item['protected_ranges_utf16']
            windows=g['native_window_ranges_utf16'];assert windows==sorted(windows,key=lambda r:(r[0],r[1]))
            cases.append({'case_id':item['case_id'],'source_id':ident,'original':t['text'],'native_words_utf16':t['native_words_utf16'],
                'native_windows_utf16':windows,'native_sentences_utf16':g['native_sentence_ranges_utf16'],
                'source_masks':t['source_masks'],'protected_ranges_utf16':t['protected_ranges_utf16'],
                'baseline_candidate_count':t['baseline_candidate_count'],'candidates':t['candidates'],
                'geometry_rejections':t['geometry_rejections'],'experimental_geometry_rejections':t['experimental_geometry_rejections'],
                'competition_removed_baseline_indices':t['competition_removed_baseline_indices'],
                'original_decisions':t['decisions'],'original_gates':q['gates'],'original_qualified_decisions':q['qualified']})
        order=json.loads(pathlib.Path(INPUTS['family_control'][0]).read_text())['learned_family_order']
        result={'schema':'vipi.native-candidate-reference.1','inputs':INPUTS,'selection_sha256':SELECTION_SHA,'cases':cases,
            'frozen_test_family_order':order,'family_order_is_not_actual_user_knowledge':True,
            'limits':'Retained exposed TRAIN observations for implementation parity only. Frozen OpenNLP roles and historical source masks differ from current native observations; compare them separately. This is not new coverage or linguistic accuracy evidence.'}
        raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();assert len(raw)<=16*1024**2
        (args.output/'reference.json').write_bytes(raw)
        receipt.update(success=True,cases=len(cases),distinct_sources=len(wanted),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),candidate_occurrences=sum(len(c['candidates']) for c in cases))
    except BaseException as exc:receipt['error']=repr(exc);raise
    finally:
        receipt.update(seconds=time.monotonic()-started,VmHWM_bytes=int(next(s.split()[1] for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024)
        (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
