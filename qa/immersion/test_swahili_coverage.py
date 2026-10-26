import copy
import unittest
from evaluate_swahili_coverage import summarize


class NativeEvidenceValidation(unittest.TestCase):
    def setUp(self):
        self.corpus = {'cases':[{'id':'one','text':{'sw':'Ninasoma kitabu.'}}], 'targets':['en']}
        self.report = {'schema':'vipi-swahili-live-catalog-coverage-1', 'rows':[
            {'id':'one','source':'sw','target':'en','original':'Ninasoma kitabu.', 'translation':'I am reading a book.',
             'exact_reference':False,'identifier_integrity':True,'elapsed_ms':1,
             'spans':[{'start':9,'end':15,'original':'kitabu','translated':'book','targetStart':15,'targetEnd':19,'reading':None}]}]}

    def test_missing_duplicate_changed_or_misscoped_evidence_is_rejected(self):
        self.assertEqual(summarize(self.report, self.corpus)['message_availability'], 1)
        changed = copy.deepcopy(self.report); changed['rows'] = []
        with self.assertRaises(ValueError): summarize(changed, self.corpus)
        changed = copy.deepcopy(self.report); changed['rows'] *= 2
        with self.assertRaises(ValueError): summarize(changed, self.corpus)
        changed = copy.deepcopy(self.report); changed['rows'][0]['original'] = 'Ninasoma kitabu?'
        with self.assertRaises(ValueError): summarize(changed, self.corpus)
        changed = copy.deepcopy(self.report); changed['rows'][0]['spans'][0]['targetStart'] = 14
        with self.assertRaises(ValueError): summarize(changed, self.corpus)

    def test_required_reading_is_not_inferred_from_execution(self):
        self.corpus['targets'] = ['ja']; self.report['rows'][0]['target'] = 'ja'
        with self.assertRaises(ValueError): summarize(self.report, self.corpus)


if __name__ == '__main__': unittest.main()
