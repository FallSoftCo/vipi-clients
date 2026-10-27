import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
import subprocess
import sys
import json
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from mapping_catalog import Catalog,digest
from export_reviewed_contexts import compile_record as exact_record
from export_reviewed_frames import compile_record,export_pair
from test_mapping_catalog import record,review
from build_wiktextract import canonical


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
            self.assertEqual(manifest['schema_version'],8)
            key.public_key().verify((folder/'manifest.sig').read_bytes(),(folder/'manifest.json').read_bytes(),ec.ECDSA(hashes.SHA256()))
            with sqlite3.connect(folder/'frames.sqlite') as db:
                self.assertEqual(db.execute('SELECT input FROM source_inputs').fetchall(),[('Buy bread',)])
                self.assertEqual(db.execute('SELECT input FROM target_inputs').fetchall(),[('Compra pan',)])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            bad=frame();bad['record']['usage']['target_frame_span']=[0,8]
            with self.assertRaises(ValueError):compile_record(bad)

    def test_unit_requires_distinct_scope_assessment_and_exact_focus(self):
        value=frame();row=value['record'];row['usage'].update(lexical_unit=True,
            source_frame_span=row['source_span'][:],target_frame_span=row['target_span'][:],
            source_frame_pattern=[{'focus':row['source']}],target_frame_pattern=[{'focus':row['target']}])
        value['sha256']=digest(row);value['assessments']=[review(row)]
        value['assessments'][0]['checks']['context_frame_scope']='pass'
        with self.assertRaises(ValueError):compile_record(value)
        value['assessments'][0]['checks']['lexical_unit_scope']='pass'
        payload,left,right=compile_record(value)
        self.assertTrue(payload['lexical_unit']);self.assertEqual(left,['bread']);self.assertEqual(right,['pan'])
        bad=copy.deepcopy(value);bad['record']['usage']['source_frame_span']=[0,9]
        with self.assertRaises(ValueError):compile_record(bad)
        with tempfile.TemporaryDirectory() as temp:
            catalog=Catalog(Path(temp)/'ledger.sqlite');identifier=catalog.register({'fixture':'unit'})
            try:
                catalog.ingest(identifier,0,[(1,row)],complete=True)
                missing=copy.deepcopy(value['assessments'][0]);del missing['checks']['lexical_unit_scope']
                with self.assertRaises(ValueError):catalog.review(missing)
                catalog.review(value['assessments'][0])
            finally:catalog.close()

    def test_lexical_carrier_cannot_silently_become_a_whole_translation(self):
        value=frame();row=value['record'];row['usage']['whole_reference']=False
        value['sha256']=digest(row);value['assessments']=[review(row)]
        value['assessments'][0]['checks']['context_frame_scope']='pass'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); signed=root/'signed';signed.mkdir()
            manifest=export_pair([value],'en','es',signed/'en-es',1,ec.generate_private_key(ec.SECP256R1()),
                'synthetic',{'records_sha256':'a'*64,'through_sequence':1})
            (signed/'receipt.json').write_text(canonical({'schema':'vipi-reviewed-frame-build-1','pairs':[manifest]}))
            subprocess.run([sys.executable,str(Path(__file__).with_name('bundle_starter_frames.py')),
                '--input',str(signed),'--output',str(root/'bundle')],check=True,capture_output=True)
            bundle=json.loads((root/'bundle/catalog.json').read_text())
            self.assertEqual(len(bundle['packs']),1)
            self.assertEqual(bundle['references'],[])
            row['usage']['whole_reference']='false'
            with self.assertRaises(ValueError):compile_record(value)

    def test_one_unit_side_keeps_the_other_side_context_bound(self):
        value=frame();row=value['record']
        row['usage'].update(lexical_unit=False,source_lexical_unit=True,target_lexical_unit=False,
            source_frame_span=row['source_span'][:],source_frame_pattern=[{'focus':row['source']}])
        value['sha256']=digest(row);value['assessments']=[review(row)]
        value['assessments'][0]['checks']['context_frame_scope']='pass'
        with self.assertRaises(ValueError):compile_record(value)
        value['assessments'][0]['checks']['lexical_unit_scope']='pass'
        payload,left,right=compile_record(value)
        self.assertFalse(payload['lexical_unit']);self.assertTrue(payload['source_lexical_unit'])
        self.assertFalse(payload['target_lexical_unit'])
        self.assertEqual(left,['bread']);self.assertEqual(right,['Compra pan'])
        for change in ({'source_lexical_unit':False},{'target_lexical_unit':True},
                       {'target_lexical_unit':None},{'source_lexical_unit':'true'},{'lexical_unit':True},
                       {'context_extent':'exact_context'}):
            bad=copy.deepcopy(value);bad['record']['usage'].update(change)
            # Rebind the assessment to exercise scope validation, not stale hashes.
            bad['sha256']=digest(bad['record']);bad['assessments']=[review(bad['record'])]
            bad['assessments'][0]['checks'].update(context_frame_scope='pass',lexical_unit_scope='pass')
            with self.assertRaises(ValueError):compile_record(bad)
        with tempfile.TemporaryDirectory() as temp:
            catalog=Catalog(Path(temp)/'ledger.sqlite');identifier=catalog.register({'fixture':'one-side-unit'})
            try:
                catalog.ingest(identifier,0,[(1,row)],complete=True)
                missing=copy.deepcopy(value['assessments'][0]);del missing['checks']['lexical_unit_scope']
                with self.assertRaises(ValueError):catalog.review(missing)
                catalog.review(value['assessments'][0])
            finally:catalog.close()


if __name__=='__main__':unittest.main()
