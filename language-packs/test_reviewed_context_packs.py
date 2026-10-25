import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from export_reviewed_contexts import compile_record, export_pair
from mapping_catalog import digest
from test_mapping_catalog import record, review


def envelope(row):return {'sha256':digest(row),'record':row,'assessments':[review(row)]}


class ReviewedContextPacksTests(unittest.TestCase):
    def test_changed_unreviewed_and_missing_readings_never_compile(self):
        good=envelope(record())
        for bad in [dict(good,sha256='0'*64),dict(good,assessments=[])]:
            with self.assertRaises(ValueError):compile_record(bad)
        bad=copy.deepcopy(good);bad['record']['target']='changed'
        with self.assertRaises(ValueError):compile_record(bad)
        bad=copy.deepcopy(good);bad['assessments'][0]['checks']['meaning']='fail'
        with self.assertRaises(ValueError):compile_record(bad)
        bad=copy.deepcopy(good);bad['assessments'][0]['evidence']=[]
        with self.assertRaises(ValueError):compile_record(bad)
        bad=copy.deepcopy(good);bad['assessments'][0]['reviewer']='synthetic-author'
        with self.assertRaises(ValueError):compile_record(bad)
        row=record(target='面包');row['target_language']='zh';row['reading']='miànbāo'
        # The ordinary synthetic assessment has not assessed a required reading.
        with self.assertRaises(ValueError):compile_record(envelope(row))

    def test_variants_preserve_focus_and_cannot_expand_without_bound(self):
        row=record();row['usage']['context_pattern']=[{'literal':'Buy '},{'focus':'bread'},
            {'literal':' on '},{'slot':['your','their','my']},{'literal':' way home.'}]
        payload,variants=compile_record(envelope(row))
        self.assertEqual(len(variants),3);self.assertIn('Buy bread on my way home.',variants)
        self.assertEqual(payload['target'],'pan')
        # Repeated alternatives still consume the bounded expansion budget.
        row['usage']['context_pattern']=[{'literal':'Buy '},{'focus':'bread'},
            {'slot':[' on ']*32},{'slot':['your']*32},{'slot':[' way home.']*32}]
        with self.assertRaises(ValueError):compile_record(envelope(row))

    def test_signed_index_retains_assessment_and_exact_matching(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'pack';key=ec.generate_private_key(ec.SECP256R1())
            row=envelope(record());manifest=export_pair([row],'en','es',folder,1,key,'test',
                {'records_sha256':'a'*64,'through_sequence':1})
            key.public_key().verify((folder/'manifest.sig').read_bytes(),(folder/'manifest.json').read_bytes(),ec.ECDSA(hashes.SHA256()))
            with sqlite3.connect(folder/'contexts.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM context_inputs WHERE input=?',('Buy bread on your way home.',)).fetchone()[0],1)
                self.assertEqual(db.execute('SELECT count(*) FROM context_inputs WHERE input=?',('Buy bread on her way home.',)).fetchone()[0],0)
                retained=json.loads(db.execute('SELECT evidence FROM mappings').fetchone()[0])
                self.assertEqual(retained,row)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertFalse(manifest['release_ready'])


if __name__=='__main__':unittest.main()
