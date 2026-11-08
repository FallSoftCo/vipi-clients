"""Bounded standalone Swahili FST feasibility. No app mutation or provider call."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, resource, shutil, subprocess, time

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/apertium-swahili-audit-r01/apertium-swa/apertium-swa.swa.lexd')
SHA = '4cc671ebd29623613e1ccf5677828c78772d215c481ef5704eeb8343ef1abab8'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SHA
parser=argparse.ArgumentParser()
parser.add_argument('--flags', action='store_true')
args=parser.parse_args()
WORK = ROOT / ('morphology-flags' if args.flags else 'morphology')
WORK.mkdir(exist_ok=False)
env = dict(os.environ, LD_LIBRARY_PATH=str(ROOT / 'prefix/usr/lib/x86_64-linux-gnu'), OMP_NUM_THREADS='1')
BIN = ROOT / 'prefix/usr/bin'
analyses = [
 ('mtu','mtu','sg'), ('watu','mtu','pl'), ('mtoto','mtoto','sg'), ('watoto','mtoto','pl'),
 ('mti','mti','sg'), ('miti','mti','pl'), ('gari','gari','sg'), ('magari','gari','pl'),
 ('kiti','kiti','sg'), ('viti','kiti','pl'), ('kisu','kisu','sg'), ('visu','kisu','pl'),
 ('nyumba','nyumba','sp'), ('rafiki','rafiki',None), ('marafiki','rafiki','pl'),
 ('kitabu','kitabu','sg'), ('vitabu','kitabu','pl'), ('chakula','chakula','sg'), ('vyakula','chakula','pl'),
 ('ninasoma','kusoma','prs'), ('nilisoma','kusoma','past'), ('nitasoma','kusoma','fut'),
 ('nimesoma','kusoma','perf'), ('wanasoma','kusoma','pl'), ('tulisoma','kusoma','past'),
 ('unasoma','kusoma','p2'), ('mnasoma','kusoma','p2'),
 ('sisomi','kusoma','neg'), ('sikusoma','kusoma','neg'), ('sitasoma','kusoma','neg'),
 ('hamsomi','kusoma','p2'), ('hamtasoma','kusoma','p2'),
 ('ninakula','kula','prs'), ('nimekuja','kuja','perf'), ('ninaenda','kuenda','prs'),
 ('soma','kusoma','imp'), ('someni','kusoma','pl'), ('kusoma','kusoma','inf'),
 ('ninasomaa',None,None), ('kitabuzzz',None,None), ('Maya',None,None), ('https://example.test/kitabu',None,None),
]
generations = [
 ('mtu<n><cl1><sg>','mtu'), ('mtu<n><cl1><pl>','watu'), ('kiti<n><cl7><sg>','kiti'), ('kiti<n><cl7><pl>','viti'),
 ('kusoma<vblex><prs><p1><sg>','ninasoma'), ('kusoma<vblex><past><p1><sg>','nilisoma'),
 ('kusoma<vblex><fut><p1><sg>','nitasoma'), ('kusoma<vblex><perf><p1><sg>','nimesoma'),
 ('kusoma<vblex><prs><neg><p1><sg><neg>','sisomi'),
 ('kusoma<vblex><fut><neg><p2><pl><neg>','hamtasoma'),
 ('kitabu<n><cl7><sg>','kitabu'), ('kitabu<n><cl7><pl>','vitabu'),
]
freeze = {'schema':'vipi.hfst-morphology-diagnostic-freeze.r01', 'production':False,
          'created_utc':datetime.now(timezone.utc).isoformat(), 'source_sha256':SHA,
          'source_revision':'4d2e6b6714e8fa2eaa3f3d74686ec683b8ee9890',
          'pipeline':'Exact orthography subset from retained lexd, without upstream spellrelax or disambiguation. Same compiled relation used for generation and inverted analysis.',
          'lexd_flags': args.flags,
          'analysis_cases':[{'surface':s,'expected_lemma':l,'expected_feature':t} for s,l,t in analyses],
          'generation_cases':[{'analysis':a,'expected_surface':s} for a,s in generations],
          'qualification_limit':'Authored morphological diagnostics, not independent language accuracy or conversation coverage; tag ABI expectations explicit.'}
(WORK/'freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(SOURCE, WORK/'source.lexd')
def limits():
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))

steps=[]
def run(tool, args=(), input_bytes=None, output=None, key=None):
    key=key or tool
    started=time.perf_counter()
    cmd=['/usr/bin/time','-f','%M', '-o', str(WORK/(key+'.rss-kib.txt')), str(BIN/tool),*map(str,args)]
    if output:
        with output.open('wb') as f:
            result=subprocess.run(cmd,input=input_bytes,stdout=f,stderr=subprocess.PIPE,env=env,preexec_fn=limits,timeout=180)
        stdout=b''
    else:
        result=subprocess.run(cmd,input=input_bytes,capture_output=True,env=env,preexec_fn=limits,timeout=180)
        stdout=result.stdout
        (WORK/(key+'.stdout.txt')).write_bytes(stdout)
    (WORK/(key+'.stderr.txt')).write_bytes(result.stderr)
    steps.append({'tool':tool,'args':[str(x) for x in args], 'key':key,'returncode':result.returncode,
                  'seconds':time.perf_counter()-started,'maxrss_kib':(WORK/(key+'.rss-kib.txt')).read_text().strip()})
    (WORK/'steps.json').write_text(json.dumps(steps,indent=2)+'\n')
    assert result.returncode==0, (key,result.stderr.decode(errors='replace')[:2000])
    assert sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()) < 256*1024**2
    return stdout

run('lexd',(['-f'] if args.flags else [])+[WORK/'source.lexd'],output=WORK/'relation.att')
run('hfst-txt2fst',['-i',WORK/'relation.att','-o',WORK/'generator.hfst'])
run('hfst-fst2fst',['-O','-i',WORK/'generator.hfst','-o',WORK/'generator.hfstol'],key='generator-optimize')
run('hfst-invert',['-i',WORK/'generator.hfst','-o',WORK/'analyzer.hfst'])
run('hfst-fst2fst',['-O','-i',WORK/'analyzer.hfst','-o',WORK/'analyzer.hfstol'],key='analyzer-optimize')
raw_analysis=run('hfst-lookup',['-q',WORK/'analyzer.hfstol'],input_bytes=('\n'.join(s for s,_,_ in analyses)+'\n').encode(),key='analysis')
raw_generation=run('hfst-lookup',['-q',WORK/'generator.hfstol'],input_bytes=('\n'.join(a for a,_ in generations)+'\n').encode(),key='generation')
def parse(raw):
    mapping={}
    for line in raw.decode().splitlines():
        parts=line.split('\t')
        if len(parts)>=2:
            mapping.setdefault(parts[0],[]).append({'output':parts[1],'weight':parts[2] if len(parts)>2 else None})
    return mapping
am,gm=parse(raw_analysis),parse(raw_generation)
ar=[]
for s,l,t in analyses:
    outputs=[p['output'] for p in am.get(s,[]) if p.get('weight')!='inf' and not p['output'].endswith('+?')]
    found= any(x.startswith(l+'<') and (not t or '<'+t+'>' in x) for x in outputs) if l else not outputs
    ar.append({'surface':s,'outputs':outputs,'expected_analysis_present_or_unknown_rejected':found})
gr=[{'analysis':a,'expected_surface':s,'outputs':gm.get(a,[]),'expected_surface_present':any(p['output']==s for p in gm.get(a,[]))} for a,s in generations]
result={'schema':'vipi.hfst-morphology-diagnostic-capture.r01','production':False,'analyses':ar,'generations':gr,'steps':steps,
        'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(WORK.iterdir()) if p.is_file()],
        'summary':{'analysis_expected_pass':sum(r['expected_analysis_present_or_unknown_rejected'] for r in ar),'analysis_total':len(ar),
                   'generation_expected_pass':sum(r['expected_surface_present'] for r in gr),'generation_total':len(gr)}}
(WORK/'capture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'summary':result['summary'],'steps':steps,'transducer_bytes':{p.name:p.stat().st_size for p in WORK.glob('*.hfstol')}},indent=2))
