"""Synthetic signed native tokenization fixtures; no production trust key."""
import argparse,base64,hashlib,json,sqlite3,tempfile
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main(output):
    if output.exists(): raise ValueError('Use a fresh fixture output')
    key=ec.generate_private_key(ec.SECP256R1());cases=[]
    examples=[('zh','明天一起喝咖啡吗？','咖啡','咖'),('ja','明日はコーヒーを飲もう。','コーヒー','コー'),('ko','내일 커피 마실래?','커피','커'),('ar','هل نشرب قهوة غدا؟','قهوة','قهو')]
    with tempfile.TemporaryDirectory() as directory:
        for source,text,expected,partial in examples:
            path=Path(directory)/(source+'.sqlite');db=sqlite3.connect(path)
            db.executescript('PRAGMA application_id=1447645257; PRAGMA user_version=1; CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID; CREATE TABLE vocabulary(source TEXT NOT NULL,target TEXT NOT NULL,part_of_speech TEXT NOT NULL,PRIMARY KEY(source,target,part_of_speech)) WITHOUT ROWID;')
            db.execute('INSERT INTO metadata VALUES (?,?)',('pack_id',source+'-en'))
            db.executemany('INSERT INTO vocabulary VALUES (?,?,?)',[(expected,'coffee','noun'),(partial,'incorrect partial match','noun')]);db.commit();db.close()
            data=path.read_bytes();manifest=json.dumps({'pack_id':source+'-en','source_language':source,'target_language':'en','revision':1,'schema_version':1,'normalization':'unicode-nfc-lower','file':'vocabulary.sqlite','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'key_id':'synthetic-lookup-qa','signature_algorithm':'ECDSA-P256-SHA256'},sort_keys=True,separators=(',',':')).encode()
            cases.append({'id':source+'-en','text':text,'expected':expected,'partial':partial,'manifest':base64.b64encode(manifest).decode(),'signature':base64.b64encode(key.sign(manifest,ec.ECDSA(hashes.SHA256()))).decode(),'database':base64.b64encode(data).decode()})
    output.write_text(json.dumps({'purpose':'SYNTHETIC NATIVE WORD LOOKUP QA ONLY','public_key':base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).decode(),'cases':cases},ensure_ascii=False)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);main(parser.parse_args().output)
