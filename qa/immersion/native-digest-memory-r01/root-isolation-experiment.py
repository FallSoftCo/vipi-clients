from pathlib import Path
import subprocess,hashlib,json,time,os,shutil,signal
r=Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01');w=r/'native-hash-memory-r01';w.mkdir(exist_ok=False);os.nice(10)
assert shutil.disk_usage(w).free>1024**3+256*1024**2
assert subprocess.run(['pgrep','-f','swift-frontend|xcodebuild'],capture_output=True).returncode==1
source='''import Foundation
import CryptoKit
import Darwin
func digest(_ url:URL,bounded:Bool)throws->String {
 let f=try FileHandle(forReadingFrom:url);defer{try? f.close()};var hash=SHA256(),total=0
 if bounded {
  while try autoreleasepool(invoking:{()throws->Bool in
   guard let data=try f.read(upToCount:1<<20),!data.isEmpty else{return false}
   total+=data.count;guard total<=512<<20 else{throw NSError(domain:"bound",code:1)}
   hash.update(data:data);return true
  }) {}
 } else {
  while let data=try f.read(upToCount:1<<20),!data.isEmpty {
   total+=data.count;guard total<=512<<20 else{throw NSError(domain:"bound",code:1)}
   hash.update(data:data)
  }
 }
 return hash.finalize().map{String(format:"%02x",$0)}.joined()
}
let bounded=CommandLine.arguments[1]=="bounded",start=DispatchTime.now().uptimeNanoseconds
var rows:[[String:String]]=[]
for path in CommandLine.arguments.dropFirst(2){rows.append(["path":path,"sha256":try digest(URL(fileURLWithPath:path),bounded:bounded)])}
var usage=rusage();getrusage(RUSAGE_SELF,&usage)
let result:[String:Any] = ["mode":bounded ? "bounded":"original","rows":rows,"seconds":Double(DispatchTime.now().uptimeNanoseconds-start)/1e9,"max_rss_bytes":usage.ru_maxrss]
let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]);FileHandle.standardOutput.write(data);print()
'''
(w/'Probe.swift').write_text(source)
receipt={'success':False,'stages':[],'source_sha256':hashlib.sha256((w/'Probe.swift').read_bytes()).hexdigest(),'disk_free_before':shutil.disk_usage(w).free,'maximum_stage_RSS_bytes':2*1024**3,'additional_disk_bytes':256*1024**2,'changes_to_app':False}
def stage(name,args,deadline):
 started=time.monotonic()
 with (w/(name+'.stdout')).open('xb') as out,(w/(name+'.stderr')).open('xb') as err:
  p=subprocess.Popen(args,stdout=out,stderr=err,start_new_session=True)
  peak=0
  try:
   while p.poll() is None:
    assert time.monotonic()-started<deadline
    assert shutil.disk_usage(w).free>=1024**3 and receipt['disk_free_before']-shutil.disk_usage(w).free<=256*1024**2
    rss=subprocess.run(['ps','-o','rss=','-p',str(p.pid)],capture_output=True,text=True)
    if rss.returncode==0 and rss.stdout.strip():peak=max(peak,int(rss.stdout.strip())*1024);assert peak<=2*1024**3
    time.sleep(.1)
   assert p.returncode==0,(name,p.returncode)
  finally:
   if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(5)
  receipt['stages'].append({'name':name,'seconds':time.monotonic()-started,'exit':p.returncode,'sampled_RSS_bytes':peak})
try:
 stage('compile',['xcrun','swiftc','-O','-num-threads','2',str(w/'Probe.swift'),'-o',str(w/'probe')],120)
 container=subprocess.check_output(['xcrun','simctl','get_app_container','46CB569D-EA59-40E3-82CC-F4A0F36EDB87','co.fallsoft.vipi','data'],text=True).strip();en=str(Path(container)/'Library/Caches/lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite');base=r/'native-candidate-producer-r01';cfg=json.loads((base/'bindings.json').read_text());es=str(Path(cfg['pack_input_directory'])/'d-es.sqlite');catalog=str(base/'catalog.sqlite')
 expected={en:'5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68',es:'fcae976ecf9a8eb79c4ea0e4e214e19894db12c8eb21959270e1b9ce78ab1e8e',catalog:'8b8198a65480a67149fc174bbc03d4eb4644ead7cb5f5aea48e050820122c9a8'}
 for mode in ['original','bounded']:
  stage(mode,[str(w/'probe'),mode,en,en,es,es,catalog,catalog],60);data=json.loads((w/(mode+'.stdout')).read_text());assert all(expected[row['path']]==row['sha256'] for row in data['rows']);receipt[mode]={k:v for k,v in data.items() if k!='rows'}
 receipt['success']=True
except BaseException as exc:receipt['error']=repr(exc)
finally:
 receipt['disk_free_after']=shutil.disk_usage(w).free;(w/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
