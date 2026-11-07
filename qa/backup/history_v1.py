"""Interoperability reference only; production codecs remain native.

History export contains no Signal state, credentials, pending sends or trust
decisions. The file is an ordered sequence of independently authenticated AES
GCM records. An authenticated final footer and strict EOF are required BEFORE
atomic import. All constants below are part of format v1, not attacker-selected.
"""
import hashlib
import io
import json
import pathlib
import struct
import time
import unicodedata
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'VIPIHST1'
ITERATIONS = 600_000
HEADER_BYTES = 36
MAX_PLAINTEXT = 262_144  # includes worst-case JSON escaping of32768UTF8bytes
MAX_FILE_BYTES = 1_073_741_824
MAX_RECORDS = 200_000
MAX_TEXT_BYTES = 32_768


def password_bytes(value):
    value = unicodedata.normalize('NFC', value)
    encoded = value.encode('utf-8', errors='strict')
    if not 12 <= len(value) or not 12 <= len(encoded) <= 1024:
        raise ValueError('password_length')
    return encoded


def key(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password_bytes(password), salt, ITERATIONS, 32)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def canonical_uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('invalid_uuid')


def integer(value, maximum=253_402_300_799_999):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('invalid_integer')


def reject_duplicates(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            raise ValueError('duplicate_json_key')
        value[k] = v
    return value


def validate_records(records, expected_account):
    if not records or records[0].keys() != {'type', 'version', 'account_id', 'created_at_ms'}:
        raise ValueError('invalid_metadata')
    metadata = records[0]
    if metadata['type'] != 'metadata' or type(metadata['version']) is not int or metadata['version'] != 1:
        raise ValueError('unsupported_format')
    canonical_uuid(metadata['account_id'])
    if metadata['account_id'] != expected_account:
        raise ValueError('different_account')
    integer(metadata['created_at_ms'])
    peers, messages = set(), set()
    for row in records[1:-1]:
        if row.get('type') == 'peer':
            if row.keys() != {'type', 'id', 'username', 'display_name'}:
                raise ValueError('invalid_peer')
            canonical_uuid(row['id'])
            if row['id'] in peers or row['id'] == expected_account or messages:
                raise ValueError('duplicate_or_misordered_peer')
            import re
            if not isinstance(row['username'], str) or re.fullmatch('[a-z][a-z0-9_]{2,23}', row['username']) is None:
                raise ValueError('invalid_username')
            name = row['display_name']
            if not isinstance(name, str) or not 1 <= len(name) <= 80 or any(unicodedata.category(c).startswith('C') for c in name):
                raise ValueError('invalid_display_name')
            peers.add(row['id'])
        elif row.get('type') == 'message':
            if row.keys() != {'type', 'id', 'peer_id', 'direction', 'sent_at_ms', 'text'}:
                raise ValueError('invalid_message')
            canonical_uuid(row['id']); canonical_uuid(row['peer_id'])
            if row['id'] in messages or row['peer_id'] not in peers or row['direction'] not in ['incoming', 'outgoing']:
                raise ValueError('invalid_message_identity')
            integer(row['sent_at_ms'])
            text = row['text']
            if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > MAX_TEXT_BYTES:
                raise ValueError('invalid_message_text')
            messages.add(row['id'])
        else:
            raise ValueError('unknown_record')
    footer = records[-1]
    if footer != {'type': 'end', 'record_count': len(records)-1, 'peer_count': len(peers), 'message_count': len(messages)}:
        raise ValueError('invalid_footer')
    for field in ['record_count', 'peer_count', 'message_count']:
        integer(footer[field], MAX_RECORDS)
    return records


def encode(records, password, salt, prefix):
    assert len(salt) == 16 and len(prefix) == 8
    validate_records(records, records[0]['account_id'])
    header = MAGIC + struct.pack('>I', ITERATIONS) + salt + prefix
    cipher = AESGCM(key(password, salt))
    result = bytearray(header)
    for index, record in enumerate(records):
        raw = json_bytes(record)
        assert len(raw) <= MAX_PLAINTEXT and index < MAX_RECORDS
        length = struct.pack('>I', len(raw)+16)
        counter = struct.pack('>I', index)
        encrypted = cipher.encrypt(prefix+counter, raw, header+counter+length)
        result += length+encrypted
    assert len(result) <= MAX_FILE_BYTES
    return bytes(result)


def decode(data, password, account):
    if not HEADER_BYTES+20 <= len(data) <= MAX_FILE_BYTES:
        raise ValueError('invalid_size')
    source = io.BytesIO(data)
    header = source.read(HEADER_BYTES)
    if header[:8] != MAGIC or int.from_bytes(header[8:12], 'big') != ITERATIONS:
        raise ValueError('unsupported_format')
    cipher = AESGCM(key(password, header[12:28]))
    records = []
    while raw_length := source.read(4):
        if len(raw_length) != 4 or len(records) >= MAX_RECORDS:
            raise ValueError('invalid_frame')
        length = int.from_bytes(raw_length, 'big')
        if not 17 <= length <= MAX_PLAINTEXT+16:
            raise ValueError('invalid_frame_size')
        encrypted = source.read(length)
        if len(encrypted) != length:
            raise ValueError('truncated_frame')
        counter = struct.pack('>I', len(records))
        clear = cipher.decrypt(header[28:36]+counter, encrypted, header+counter+raw_length)
        row = json.loads(clear.decode('utf-8', errors='strict'), object_pairs_hook=reject_duplicates)
        if not isinstance(row, dict):
            raise ValueError('invalid_record')
        records.append(row)
        if row.get('type') == 'end':
            if source.read(1):
                raise ValueError('trailing_data')
            return validate_records(records, account)
    raise ValueError('missing_footer')


def main():
    folder = pathlib.Path(__file__).parent
    account = '11111111-1111-4111-8111-111111111111'
    peer = '22222222-2222-4222-8222-222222222222'
    records = [
        {'type':'metadata','version':1,'account_id':account,'created_at_ms':1794089000000},
        {'type':'peer','id':peer,'username':'rafiki','display_name':'Rafiki 日本語'},
        {'type':'message','id':'33333333-3333-4333-8333-333333333333','peer_id':peer,'direction':'incoming','sent_at_ms':1794088000000,'text':'Habari! Tutaonana kesho. 👋'},
        {'type':'message','id':'44444444-4444-4444-8444-444444444444','peer_id':peer,'direction':'outgoing','sent_at_ms':1794088100000,'text':'See you tomorrow. 日本語 العربية café'},
        {'type':'end','record_count':4,'peer_count':1,'message_count':2},
    ]
    vectors = []
    for name, password in [('ascii','correct horse vipi 2026'),('unicode','Vipi café 日本語 🔐 2026')]:
        salt=bytes(range(16));prefix=bytes(range(160,168))
        started=time.perf_counter();blob=encode(records,password,salt,prefix);elapsed=time.perf_counter()-started
        assert decode(blob,password,account)==records
        assert decode(blob,unicodedata.normalize('NFD',password),account)==records
        file=folder/(name+'.vipihistory');file.write_bytes(blob)
        vectors.append({'file':file.name,'sha256':hashlib.sha256(blob).hexdigest(),'password':password,'nfd_password':unicodedata.normalize('NFD',password),'salt_hex':salt.hex(),'nonce_prefix_hex':prefix.hex(),'derived_key_hex':key(password,salt).hex(),'bytes':len(blob),'encode_seconds_reference_host':elapsed})
    invalid = {
        'truncated_footer':blob[:-1],
        'missing_footer':blob[:-len(json_bytes(records[-1]))-20],
        'trailing_data':blob+b'x',
        'tampered_header':blob[:28]+bytes([blob[28]^1])+blob[29:],
        'tampered_ciphertext':blob[:55]+bytes([blob[55]^1])+blob[56:],
        'unsupported_iterations':blob[:8]+struct.pack('>I',1)+blob[12:],
        'oversized_frame':blob[:36]+struct.pack('>I',MAX_PLAINTEXT+17)+blob[40:],
    }
    for name,bad in invalid.items():
        try:decode(bad,password,account)
        except Exception:pass
        else:raise AssertionError(name)
    for bad_password,bad_account in [('wrong password 2026',account),(password,peer)]:
        try:decode(blob,bad_password,bad_account)
        except Exception:pass
        else:raise AssertionError('acceptedwrongcredentials')
    (folder/'vectors.json').write_text(json.dumps({'test_only':True,'records':records,'vectors':vectors,'negative_cases':list(invalid)+['wrong_password','different_account']},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'vectors':len(vectors),'negative_cases':len(invalid)+2,'bytes':[v['bytes'] for v in vectors]}))


if __name__=='__main__':main()
