"""Reviewed starter displayed-form HMAC oracle, synthetic vectors only."""
import hashlib,hmac,json
from pathlib import Path
FIELDS=('version','source_language','target_language','entry_id','concept_id','pos','guard','canonical_source','target_face','reading')
def encode(fields):
    out=b''
    for name in FIELDS:
        value=fields[name]
        if not isinstance(value,str):raise ValueError(name)
        data=value.encode('utf-8');out+=len(data).to_bytes(4,'big')+data
    return out

def identity(case,key):
    if not case['verified_current_occurrence']:return None
    return hmac.new(key,encode(case['fields']),hashlib.sha256).hexdigest()

if __name__=='__main__':
    x=json.loads(Path(__file__).with_name('starter-identity-fixtures.json').read_text());key=bytes.fromhex(x['test_key_hex']);assert len(key)==32
    cases={r['id']:r for r in x['cases']}
    for row in cases.values():
        got=identity(row,key);assert got==row['expected_hmac_sha256'],row['id']
        if got is not None:assert encode(row['fields']).hex()==row['expected_encoded_hex']
    for r in x['relations']:assert (identity(cases[r['a']],key)==identity(cases[r['b']],key))==r['equal'],r
    print(f"{len(cases)} synthetic starter vectors, {len(x['relations'])} relationships pass; no native display or vault proof")
