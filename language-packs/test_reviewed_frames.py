import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from mapping_catalog import Catalog,digest
from export_reviewed_contexts import compile_record as exact_record
from export_reviewed_frames import compile_record,export_pair
from test_mapping_catalog import record,review


def frame():
    row=record();row['usage'].update(context_extent='local_phrase',source_frame_span=[0,9],target_frame_span=[0,10],
        permitted_context='Synthetic qualification: bread as food within a purchase construction.',
        abstain_when=['No corresponding target purchase phrase.'])
    assessment=review(row);assessment['checks']['context_frame_scope']='pass'
    return {'record':row,'sha256':digest(row),'assessments':[assessment]}


class ReviewedFrameTests(unittest.TestCase):
    def test_exact_context_approval_cannot_be_reused_for_phrase_matching(self):
        value=frame();payload,left,right=compile_record(value)
        self.assertEqual(left,['Buy bread']);self.assertEqual(right,['Compra pan'])
        with self.assertRaises(ValueError):exact_record(value)
        bad=copy.deepcopy(value);del bad['assessments'][0]['checks']['context_frame_scope']
        with self.assertRaises(ValueError):compile_record(bad)
        with tempfile.TemporaryDirectory() as temp:
            catalog=Catalog(Path(temp)/'ledger.sqlite');identifier=catalog.register({'fixture':'phrase'})
            try:
                catalog.ingest(identifier,0,[(1,value['record'])],complete=True)
                with self.assertRaises(ValueError):catalog.review(bad['assessments'][0])
                catalog.review(value['assessments'][0])
                self.assertEqual(catalog.export_reviewed(Path(temp)/'exact','exact_context')['records'],0)
                self.assertEqual(catalog.export_reviewed(Path(temp)/'phrase','local_phrase')['records'],1)
            finally:catalog.close()

    def test_signed_pack_keeps_both_indexes_and_bounds_focus(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'pack';key=ec.generate_private_key(ec.SECP256R1())
            manifest=export_pair([frame()],'en','es',folder,1,key,'synthetic',{'records_sha256':'a'*64,'through_sequence':1})
            self.assertEqual(manifest['schema_version'],6)
            key.public_key().verify((folder/'manifest.sig').read_bytes(),(folder/'manifest.json').read_bytes(),ec.ECDSA(hashes.SHA256()))
            with sqlite3.connect(folder/'frames.sqlite') as db:
                self.assertEqual(db.execute('SELECT input FROM source_inputs').fetchall(),[('Buy bread',)])
                self.assertEqual(db.execute('SELECT input FROM target_inputs').fetchall(),[('Compra pan',)])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            bad=frame();bad['record']['usage']['target_frame_span']=[0,8]
            with self.assertRaises(ValueError):compile_record(bad)


if __name__=='__main__':unittest.main()
