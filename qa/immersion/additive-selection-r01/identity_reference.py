"""Synthetic cross-platform exposure identity oracle. No real user data."""
import hashlib,hmac,json
from pathlib import Path
FIELDS=('version','source_language','target_language','pattern_id','source_face','target_face','meaning','reading')
def encode(fields):
    output=b''
    for name in FIELDS:
        value=fields[name]
        if not isinstance(value,str):raise ValueError(name)
        data=value.encode('utf-8');output+=len(data).to_bytes(4,'big')+data
    return output

def identity(fields,key):
    return hmac.new(key,encode(fields),hashlib.sha256).hexdigest()

def validate(case,key):
    if not case['verified_reviewed_pattern']:return None
    return identity(case['fields'],key)

if __name__=='__main__':
    x=json.loads(Path(__file__).with_name('identity-fixtures.json').read_text());key=bytes.fromhex(x['test_key_hex'])
    assert len(key)==32
    for case in x['cases']:
        result=validate(case,key)
        assert result==case['expected_hmac_sha256'],(case['id'],result)
        if result is not None:assert encode(case['fields']).hex()==case['expected_encoded_hex']
    for group in x['relations']:
        cases={c['id']:c for c in x['cases']};a=validate(cases[group['a']],key);b=validate(cases[group['b']],key)
        assert (a==b)==group['equal'],group
    print(f"{len(x['cases'])} synthetic identity vectors and {len(x['relations'])} relationships pass; no native vault evidence")
