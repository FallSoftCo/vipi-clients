#!/usr/bin/env python3
"""Additive read-only quality accounting by fixed input provenance."""
import json,hashlib,collections
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def main():
 joined=json.loads((W/'joined-r01/joined.json').read_text());key=json.loads((W/'review-r01/method-key.json').read_text());packet=json.loads((W/'review-r01/anonymous-packet.json').read_text());groups={(c['pair'],c['id']):c['stratum'] for c in packet['cases']};labels={}
 for reviewer,review in joined['original_reviews'].items():
  for c in review['cases']:
   for o in c['options']:labels[reviewer,c['pair'],c['id'],o['label']]={'material':'material_error','minor':'minor_issue'}.get(o['judgment'],o['judgment'])
 counts=collections.defaultdict(collections.Counter)
 for x in key:
  if x['route']!='route' or x['state']!='none' or x['density_bits'] not in ['3fd0000000000000','3fe8000000000000']:continue
  for reviewer in joined['original_reviews']:
   k=(reviewer,x['platform'],x['pair'],groups[x['pair'],x['id']],x['density_bits'],x['arm']);counts[k][labels[reviewer,x['pair'],x['id'],x['label']]]+=1
 out=W/'joined-r01/strata.json';assert not out.exists();out.write_text(json.dumps({'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'joined_sha256':hashlib.sha256((W/'joined-r01/joined.json').read_bytes()).hexdigest(),'rows':[{'key':list(k),**v} for k,v in sorted(counts.items())]},sort_keys=True,indent=2)+'\n')
 for k,v in sorted(counts.items()):
  if k[0]=='root' and k[1]=='android' and k[4]=='3fd0000000000000':print(k[2],k[3],k[5],dict(v))
if __name__=='__main__':main()
