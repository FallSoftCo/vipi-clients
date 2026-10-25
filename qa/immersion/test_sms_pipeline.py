import copy
import unittest
from evaluate_sms_pipeline import summarize


class PipelineEvidenceTests(unittest.TestCase):
    def fixtures(self):
        corpus={'languages':['en','zh'],'cases':[{'id':'a','text':{'en':'A book.'}}]}
        span={'start':2,'end':6,'original':'book','translated':'书','reading':'shū','targetStart':2,'targetEnd':3}
        sample={'id':'a','original':'A book.','translation':'一本书。','status':'executed',
            'candidate_senses':2,'lookup_alignment_ms':1.0,'spans':[span],'context_candidates':[span]}
        return corpus,{'results':[{'source':'en','target':'zh','status':'executed','samples':[sample]}]}

    def test_complete_case_identity_and_offsets_are_required(self):
        corpus,report=self.fixtures()
        result=summarize(report,corpus)
        self.assertEqual(result['totals']['messages_with_spans'],1)
        missing=copy.deepcopy(report);missing['results'][0]['samples']=[]
        with self.assertRaises(ValueError):summarize(missing,corpus)
        wrong=copy.deepcopy(report);wrong['results'][0]['samples'][0]['spans'][0]['end']=5
        with self.assertRaises(ValueError):summarize(wrong,corpus)

    def test_missing_readings_cannot_count_as_usable_nonroman_output(self):
        corpus,report=self.fixtures()
        report['results'][0]['samples'][0]['spans'][0]['reading']=''
        with self.assertRaises(ValueError):summarize(report,corpus)


if __name__=='__main__':unittest.main()
