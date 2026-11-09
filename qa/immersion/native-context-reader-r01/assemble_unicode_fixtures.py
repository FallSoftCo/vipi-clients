#!/usr/bin/env python3
"""Reconstruct the separate fixture assembly step; default verifies without writes.

1. generate_unicode.py runs under frozen production Python3.12.3/Unicode15.0.0
   and emits unicode-generated.json (tables + scalar-token expected outputs).
2. THIS separate assembly step runs under system76 Python3.12.6/Unicode15.0.0.
   It adds per-case whole-string NFC/casefold/whitespace-collapse expectations,
   assembles tokenizer-fixtures.json, and embeds exact table/fixture bytes in Swift.
   No native inference or tests are performed by either data-only recipe.

Usage: python3 assemble_unicode_fixtures.py EVIDENCE_DIRECTORY [--write-new]
--write-new requires the three destination files to be absent; no overwrites.
The remaining Swift sources/tests are authored retained sources, not outputs of
this generator. Their exact identities are in final-sources and hash inventory.
"""
import argparse,base64,hashlib,json,pathlib,sys,unicodedata
p=argparse.ArgumentParser();p.add_argument('directory',type=pathlib.Path);p.add_argument('--write-new',action='store_true');a=p.parse_args()
assert sys.version_info[:3]==(3,12,6),sys.version
assert unicodedata.unidata_version=='15.0.0'
d=json.loads((a.directory/'unicode-generated.json').read_text())
raw=json.dumps(d['tables'],separators=(',',':')).encode()
assert hashlib.sha256(raw).hexdigest()==d['table_sha256']
table_source='// Generated from exact frozen Python3.12.3 / Unicode15.0.0; see generation receipt.\nenum FrozenContextUnicodeTables {\n static let sha256 = "'+d['table_sha256']+'"\n static let base64 = "'+base64.b64encode(raw).decode()+'"\n}\n'
for row in d['probes']:
 row['normalized']=' '.join(unicodedata.normalize('NFC',row['source']).casefold().split())
fixtures={'schema':'vipi.frozen-context-tokenizer-parity.r01','unicode_version':'15.0.0','table_sha256':d['table_sha256'],'token_probes_runtime':d['runtime'],'whole_normalization_expected_runtime':'Python3.12.6 Unicode15.0.0, same pinned Unicode database','cases':d['probes']}
data=json.dumps(fixtures,ensure_ascii=True,separators=(',',':')).encode()
fixture_source='enum FrozenContextTokenizerFixture {\n static let sha256 = "'+hashlib.sha256(data).hexdigest()+'"\n static let base64 = "'+base64.b64encode(data).decode()+'"\n}\n'
outputs={'FrozenContextUnicodeTables.swift':table_source.encode(),'tokenizer-fixtures.json':data,'FrozenContextTokenizerFixture.swift':fixture_source.encode()}
for name,content in outputs.items():
 path=a.directory/name
 if a.write_new:
  with path.open('xb') as f:f.write(content)
 else:assert path.read_bytes()==content,name
print(json.dumps({'mode':'write_new' if a.write_new else 'verify_reconstruction','assembly_python':sys.version,'unicode_version':unicodedata.unidata_version,'input_sha256':hashlib.sha256((a.directory/'unicode-generated.json').read_bytes()).hexdigest(),'outputs':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in outputs.items()}},indent=2))
