import json
from pathlib import Path
import tempfile
import unittest

from mapping_catalog import Catalog, digest, import_records


def record(identity='bread', target='pan'):
    return {'schema':'vipi-contextual-mapping-1','logical_id':identity,
        'source_language':'en','target_language':'es','source':'bread','target':target,'reading':'',
        'source_context':'Buy bread on your way home.','target_context':'Compra '+target+' de camino a casa.',
        'source_span':[4,9],'target_span':[7,7+len(target)],'meaning':'bread as food',
        'usage':{'focus_is_lexical':True,'person':'outside_focus'},
        'provenance':{'author':'synthetic-author','license':'synthetic-test-only'}}


def review(row, verdict='reviewed'):
    return {'schema':'vipi-mapping-review-1','record_sha256':digest(row),'reviewer':'synthetic-reviewer',
        'assessment_kind':'independent_assessment',
        'verdict':verdict,'evidence':[{'sha256':'a'*64,'description':'Synthetic assessment for ledger mechanics only'}],
        'checks':{'meaning':'pass','usage':'pass','grammar_scope':'pass','provenance':'pass','reading':'not_required'}}


class MappingCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.path=self.root/'ledger.sqlite'; self.catalog=Catalog(self.path)

    def tearDown(self):
        self.catalog.close(); self.temp.cleanup()

    def test_record_and_checkpoint_rollback_together(self):
        source=self.catalog.register({'source':'one'})
        bad=record('bad'); bad['target_span']=[0,500]
        with self.assertRaises(ValueError): self.catalog.ingest(source,0,[(1,record()),(2,bad)])
        self.assertEqual(self.catalog.position(source),(0,False))
        self.assertEqual(self.catalog.stats()['revisions'],0)
        self.assertEqual(self.catalog.stats()['sequence'],0)

    def test_resume_after_reopen_and_deduplicate_second_input(self):
        source=self.catalog.register({'source':'one'})
        self.catalog.ingest(source,0,[(1,record())])
        self.catalog.close(); self.catalog=Catalog(self.path)
        self.catalog.ingest(source,1,[(2,record('two'))],complete=True)
        again=self.catalog.register({'source':'two'})
        result=self.catalog.ingest(again,0,[(1,record()),(2,record('two'))],complete=True)
        self.assertEqual(result['inserted'],0)
        self.assertEqual(self.catalog.stats()['revisions'],2)
        self.assertEqual(self.catalog.stats()['sequence'],2)

    def test_stale_worker_cannot_commit_same_batch_again(self):
        source=self.catalog.register({'source':'one'})
        other=Catalog(self.path)
        try:
            self.catalog.ingest(source,0,[(1,record())])
            with self.assertRaises(ValueError): other.ingest(source,0,[(1,record())])
            self.assertEqual(other.position(source),(1,False))
        finally: other.close()

    def test_revision_change_requires_its_own_review(self):
        original=record(); changed=record(target='un pan')
        first=self.catalog.register({'source':'one'})
        self.catalog.ingest(first,0,[(1,original)],complete=True)
        self.catalog.review(review(original))
        before=self.catalog.export_reviewed(self.root/'before')
        self.assertEqual(before['records'],1)
        second=self.catalog.register({'source':'two'})
        self.catalog.ingest(second,0,[(1,changed)],complete=True)
        self.catalog.review(review(original))  # idempotent old assessment
        self.assertEqual(self.catalog.export_reviewed(self.root/'after')['records'],0)
        self.assertEqual(self.catalog.stats()['states'],{'candidate':1})

    def test_old_resume_and_historical_reimport_cannot_roll_back_a_head(self):
        old=self.catalog.register({'source':'old'})
        new=self.catalog.register({'source':'new'})
        a=record(); b=record(target='un pan')
        self.catalog.ingest(new,0,[(1,b)],complete=True)
        self.catalog.ingest(old,0,[(1,a)],complete=True)
        latest=self.catalog.register({'source':'old-content-new-file'})
        self.catalog.ingest(latest,0,[(1,a)],complete=True)
        current=self.catalog.db.execute('SELECT sha256 FROM heads').fetchone()[0]
        self.assertEqual(current,digest(b))
        self.assertEqual(self.catalog.stats()['revisions'],2)

    def test_quarantine_removes_current_export_and_preserves_history(self):
        source=self.catalog.register({'source':'one'}); value=record()
        self.catalog.ingest(source,0,[(1,value)],complete=True)
        self.catalog.review(review(value)); self.catalog.review(review(value,'quarantined'))
        self.assertEqual(self.catalog.export_reviewed(self.root/'quarantined')['records'],0)
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM reviews').fetchone()[0],2)
        self.assertEqual(self.catalog.stats()['states'],{'quarantined':1})

    def test_false_independence_missing_gates_and_stale_digest_do_not_qualify(self):
        value=record(); source=self.catalog.register({'source':'one'})
        self.catalog.ingest(source,0,[(1,value)],complete=True)
        for mutate in [lambda x:x.update(reviewer='synthetic-author'),
                       lambda x:x['checks'].pop('meaning'),
                       lambda x:x.update(record_sha256='f'*64),
                       lambda x:x.update(evidence=[])]:
            assessment=review(value); mutate(assessment)
            with self.assertRaises(ValueError): self.catalog.review(assessment)
        self.assertEqual(self.catalog.stats()['states'],{'candidate':1})

    def test_author_assessment_is_explicit_and_export_retains_its_limit(self):
        value=record(); source=self.catalog.register({'source':'one'})
        self.catalog.ingest(source,0,[(1,value)],complete=True)
        assessment=review(value)
        assessment.update(reviewer='synthetic-author',assessment_kind='author_assessment')
        self.catalog.review(assessment)
        result=self.catalog.export_reviewed(self.root/'author-assessed')
        self.assertEqual(result['records'],1)
        self.assertFalse(result['release_ready'])
        exported=json.loads((self.root/'author-assessed/records.jsonl').read_text())
        self.assertEqual(exported['assessments'][0]['assessment_kind'],'author_assessment')

    def test_non_roman_missing_reading_cannot_qualify(self):
        value=record(target='パン'); value['target_language']='ja'
        value['target_context']='パンを買ってください。'; value['target_span']=[0,2]
        source=self.catalog.register({'source':'one'})
        self.catalog.ingest(source,0,[(1,value)],complete=True)
        assessment=review(value); assessment['checks']['reading']='pass'
        with self.assertRaises(ValueError): self.catalog.review(assessment)
        self.assertEqual(self.catalog.stats()['states'],{'candidate':1})

    def test_jsonl_batches_resume_at_exact_unicode_byte_offsets(self):
        path=self.root/'input.jsonl'
        values=[record('one'),record('two',target='café')]
        path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in values))
        source=import_records(self.catalog,path,1,1)
        self.assertFalse(self.catalog.position(source)[1])
        self.assertEqual(self.catalog.stats()['current_records'],1)
        import_records(self.catalog,path,1,0)
        self.assertEqual(self.catalog.position(source),(path.stat().st_size,True))
        self.assertEqual(self.catalog.stats()['current_records'],2)
        import_records(self.catalog,path,1,0)
        self.assertEqual(self.catalog.stats()['current_records'],2)


if __name__=='__main__': unittest.main()
