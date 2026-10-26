import copy
import unittest
from compare_native_probe import compare


class NativeComparisonTests(unittest.TestCase):
    def test_different_translations_or_cases_cannot_be_reported_as_pack_improvement(self):
        before={'platform':'synthetic','results':[{'source':'en','target':'es','samples':[
            {'id':'a','status':'executed','original':'Books.','translation':'Libros.','spans':[]}]}]}
        self.assertEqual(compare(before,copy.deepcopy(before)),[])
        after=copy.deepcopy(before);after['results'][0]['samples'][0]['translation']='Changed.'
        with self.assertRaises(ValueError):compare(before,after)
        after=copy.deepcopy(before);after['results'][0]['samples'][0]['id']='b'
        with self.assertRaises(ValueError):compare(before,after)


if __name__=='__main__':unittest.main()
