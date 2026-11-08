from pathlib import Path
import subprocess,json,hashlib,time,sys,shutil
q=Path(__file__).resolve().parent;p=Path('/home/ai/Development/investigations/vipi-android-opennlp-runtime-20261108-r01');variant=sys.argv[1];assert variant in ['Debug','Release'];d=p/variant.lower();d.mkdir(exist_ok=False);adb=['adb','-s','emulator-5620'];pkg='co.fallsoft.vipi.opennlpqa';x={'variant':variant,'steps':[],'complete':False,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
def save():(d/'runner.json').write_text(json.dumps(x,indent=2)+'\n')
def run(args,timeout=30):
 r=subprocess.run(adb+args,capture_output=True,timeout=timeout);x['steps'].append({'args':args,'exit':r.returncode,'stdout_bytes':len(r.stdout),'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr':r.stderr.decode(errors='replace')});save();assert r.returncode==0,(args,r.stderr.decode());return r.stdout
try:
 assert run(['shell','getprop','ro.build.version.sdk']).strip()==b'35';x['abi']=run(['shell','getprop','ro.product.cpu.abi']).decode().strip();assert x['abi']=='x86_64'
 assert run(['emu','avd','name']).decode().splitlines()[0]=='pocket_verify_api35'
 apk=p/f'project/app/build/outputs/apk/{variant.lower()}/app-{variant.lower()}.apk';assert apk.is_file();x['apk_sha256']=hashlib.sha256(apk.read_bytes()).hexdigest();x['apk_bytes']=apk.stat().st_size;save()
 assert shutil.disk_usage(p).free>8589934592
 run(['install','-r',str(apk)],60)
 remote=run(['shell','pm','path',pkg]).decode().strip().removeprefix('package:');assert run(['shell','sha256sum',remote]).decode().split()[0]==x['apk_sha256']
 package=run(['shell','dumpsys','package',pkg]);(d/'package.txt').write_bytes(package);assert b'android.permission.INTERNET' not in package;x['no_internet_permission']=True
 run(['shell','am','force-stop',pkg]);save()
 result=run(['shell','am','instrument','-w',pkg+'/'+pkg+'.ProbeInstrumentation'],120);(d/'instrument.log').write_bytes(result)
 rows=[];reports=[]
 for line in result.decode().splitlines():
  if 'OPENNLP_ROW:' in line:rows.append(line.split('OPENNLP_ROW:',1)[1])
  if 'OPENNLP_RECEIPT:' in line:reports.append(line.split('OPENNLP_RECEIPT:',1)[1])
 assert len(reports)==1,'missing/duplicate instrumentation final receipt'
 (d/'receipt.json').write_text(reports[0]+'\n');(d/'annotations.jsonl').write_text('\n'.join(rows)+'\n')
 report=json.loads((d/'receipt.json').read_text());x['native_success']=report['success'];x['output_sha256']=hashlib.sha256((d/'annotations.jsonl').read_bytes()).hexdigest();x['complete']=True
except Exception as e:x['error']=repr(e)
finally:save();print(json.dumps({k:v for k,v in x.items() if k!='steps'},indent=2))
