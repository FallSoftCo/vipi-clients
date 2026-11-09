"""Prepare isolated source only; never edit canonical app or execute alignment."""
import pathlib,subprocess,hashlib,json
Q=pathlib.Path(__file__).resolve().parent;W=pathlib.Path('/home/ai/Development/investigations/vipi-target-informed-alignment-20261109-r01')
base=subprocess.check_output(['git','show','0d2451a:ios/Vipi/LexicalConcordance.swift']).decode();inc=(Q/'target_informed.swift.inc').read_text()
a=base.index('            struct Claim:Hashable {let range:NSRange,reading:String}',base.index('    private static func lookup('));b=base.index('            if let witnessDB {',a)
replacement='            var output=try targetInformedEntries(left:left,right:right,original:original,translation:translation,source:source,target:target,alignment:alignment,diagnostic:diagnostic)\n'
patched=base[:a]+replacement+base[b:];pos=patched.index('    private static func lookup(');patched=patched[:pos]+inc+'\n'+patched[pos:]
# Preserve unchanged witness-stage behavior; graph claim-only records must not
# masquerade as accepted strict candidates inside its skip/ownership decisions.
patched=patched.replace('strict:output,alignment:alignment','strict:output.filter{!$0.requiresContext},alignment:alignment')
(W/'LexicalConcordance.baseline.swift').write_text(base);(W/'LexicalConcordance.experimental.swift').write_text(patched)
r={'base_commit':'0d2451a','base_sha256':hashlib.sha256(base.encode()).hexdigest(),'experimental_sha256':hashlib.sha256(patched.encode()).hexdigest(),'increment_sha256':hashlib.sha256(inc.encode()).hexdigest(),'executed':False,'canonical_files_modified':False}
(W/'patch-preparation.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
