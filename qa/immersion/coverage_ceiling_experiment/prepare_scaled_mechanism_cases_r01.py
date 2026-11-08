#!/usr/bin/env python3
"""TRAIN-only representative mechanisms, not a new candidate or validation sample."""
import argparse,hashlib,json,re,sqlite3
from pathlib import Path
Q=Path(__file__).resolve().parent
WORDS=['like','live','coffee','parents','shopping','currently','either','interesting','birthday','hospital']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);p.add_argument('--candidate-db',type=Path,required=True);p.add_argument('--train',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(exist_ok=False);audit=json.loads(a.audit.read_text());src={r['source']:r for r in audit['source_rows']};train=json.loads(a.train.read_text());assert sha(a.train)=='a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c';db=sqlite3.connect(a.candidate_db.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;rows=[];wanted={}
 for word in WORDS:
  matches=[]
  for ci,c in enumerate(train):
   if c['context_dataset']!='convai2':continue
   for ti,(speaker,text) in enumerate(c['dialog']):
    if speaker==0 and re.search(r'\b'+re.escape(word)+r'\b',text,re.I):matches.append({'id':f'bst-train-{ci:04d}-{ti:02d}','text':text,'preceding_context_for_review':c['dialog'][:ti]})
  links=[dict(r) for r in db.execute('SELECT * FROM candidates WHERE source=? ORDER BY target_language,sense,target,reading',(word,))];rows.append({'source':word,'TRAIN_rank':src[word]['rank'],'TRAIN_occurrences':src[word]['TRAIN_occurrences'],'examples':matches[:2],'sampling':'First two exact-form free-human TRAIN occurrences in original corpus order; mechanisms deliberately selected after inventory inspection, not a blind or prevalence sample.','source_audit':src[word],'all_target_alternatives':links})
  for r in links:
   if r['target_language'] in ['es','ja','sw'] and r['pos_compatible']:wanted[r['target_lexeme']]={'language':r['target_language'],'headword':r['target']}
 for r in db.execute("SELECT DISTINCT target_lexeme,target FROM candidates WHERE source='buying' AND target_language='sw' AND target='ununuzi'"):
  wanted[r[0]]={'language':'sw','headword':r[1],'reason':'Potential missing shopping/buying link; inspect actual primary sense, do not infer equivalence from target spelling.'}
 db.close();out={'production':False,'new_candidate':False,'training_only':True,'purpose':'Ten representative mechanisms before the next candidate: full alternatives and primary evidence, structural gaps versus contextual sense/form decisions. Birthday/hospital are lower-frequency explanatory controls; ranks/counts explicit.','input_sha256':{str(p):sha(p) for p in [a.audit,a.candidate_db,a.train,Path(__file__)]},'cases':rows};f=a.output_dir/'cases.json';f.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');req={'production':False,'source_case_sha256':sha(f),'expected_inventory_sha256':'8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17','records':{str(k):v for k,v in sorted(wanted.items())}};(a.output_dir/'primary-target-request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2)+'\n');print(sha(f),len(wanted))
if __name__=='__main__':main()
