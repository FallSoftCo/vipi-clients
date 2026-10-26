import copy
import unittest
from subset_native_probe import subset


class PairViewTests(unittest.TestCase):
    def test_pair_view_keeps_case_identity_and_rejects_missing_or_changed_capture(self):
        corpus={'version':'synthetic','languages':['en','es','fr'],'cases':[{'id':'a','text':{'en':'Books.'}},{'id':'b','text':{'fr':'Livres.'}}]}
        capture={'results':[{'source':'en','target':'es','samples':[{'id':'a','original':'Books.','translation':'Libros.','status':'executed'}]}]}
        view,report=subset(corpus,capture,'en','es')
        self.assertEqual(view['cases'],[corpus['cases'][0]])
        self.assertEqual(report['expected_pairs'],1)
        wrong=copy.deepcopy(capture);wrong['results'][0]['samples'][0]['original']='Changed.'
        with self.assertRaises(ValueError):subset(corpus,wrong,'en','es')
        wrong=copy.deepcopy(capture);wrong['results'][0]['samples']=[]
        with self.assertRaises(ValueError):subset(corpus,wrong,'en','es')
        self.assertEqual(len(corpus['cases']),2)


if __name__=='__main__':unittest.main()
