import pathlib,json,subprocess,shlex,hashlib
w=pathlib.Path(__file__).parent;p=w.parent/'vipi-target-informed-taskmaster-20261109-r01';raw=json.loads((p/'run-r02/output.json').read_text());edges=[]
for r in raw['cases']:
 for k,n in r.get('lexical_diagnostics_aggregate_not_focus_labels',{}).items():
  if k.startswith('target_graph:'):
   d=json.loads(k[len('target_graph:'):])
   if d.get('kind')=='edge':edges.append({'id':r['id'],'edge':d,'proof_count':n})
assert len({(e["id"],tuple(e["edge"]["source"]),tuple(e["edge"]["target"])) for e in edges})==172
ids=sorted({int(r['edge']['source_lexeme']) for r in edges})
code='''import sqlite3,json,sys,socket,resource,os
assert socket.gethostname()=='fallsoft-production-20261106';resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30));resource.setrlimit(resource.RLIMIT_CPU,(60,60));os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10)
p='/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01/inputs/d-en.sqlite';d=sqlite3.connect('file:'+p+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
ids=json.loads(sys.stdin.read());out=[]
for i in ids:
 l=dict(d.execute('SELECT * FROM lexemes WHERE id=?',(i,)).fetchone());f=[dict(x) for x in d.execute('SELECT * FROM surfaces WHERE lexeme=?',(i,))];out.append({'lexeme':l,'forms':f})
print(json.dumps({'path':p,'qualified_sha256':'5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68','fresh_full_hash':False,'rows':out}))
'''
a=subprocess.run(['ssh','-o','ConnectTimeout=15','fallsoft-production','python3 -B -c '+shlex.quote(code)],input=json.dumps(ids),text=True,capture_output=True,timeout=70)
(w/'dictionary-query-receipt.json').write_text(json.dumps({'query':code,'ids':ids,'exit_code':a.returncode,'stderr':a.stderr},indent=2)+'\n');assert a.returncode==0,a.stderr
(w/'source-dictionary-forms.json').write_text(a.stdout);(w/'edges-172.json').write_text(json.dumps(edges,indent=2)+'\n');print(len(ids),len(a.stdout))
