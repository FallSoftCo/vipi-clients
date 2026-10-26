import copy
import unittest
from incremental_phrase_probe import changed,combine


class IncrementalPhraseTests(unittest.TestCase):
    def test_changed_focus_and_provider_inputs_cannot_reuse_old_outputs(self):
        row={'case':'one','source':'en','target':'es','original':'a dog','source_word':'dog','start':2,'end':5}
        base={'schema':'probe','window_extents':[],'maximum_phrase_characters':192,'maximum_window_words':8,'samples':[row]}
        full=copy.deepcopy(base);full['samples'] += [dict(row,case='two',original='my dog',start=3,end=6)]
        delta=dict(full,samples=changed(base,full))
        def capture(protocol,sha):return {'protocol_sha256':sha,'complete':True,'provider':'test','network_absence_verified':True,
            'cases_expected':len(protocol['samples']),'cases_completed':len(protocol['samples']),
            'results':[dict(r,status='executed',translation='perro') for r in protocol['samples']]}
        old=capture(base,'b');new=capture(delta,'d')
        hashes={'base_protocol':'b','full_protocol':'f','delta_protocol':'d','base_capture':'old','delta_capture':'new'}
        result=combine(base,full,delta,old,new,hashes)
        self.assertEqual(result['reused_cases'],1);self.assertEqual(result['delta_cases'],1)
        self.assertEqual([r['capture_provenance_sha256'] for r in result['results']],['old','new'])
        altered=copy.deepcopy(full);altered['samples'][0]['start']=1
        self.assertEqual(len(changed(base,altered)),2)
        with self.assertRaises(ValueError):combine(base,altered,delta,old,new,hashes)
        bad=copy.deepcopy(new);bad['provider']='other'
        with self.assertRaises(ValueError):combine(base,full,delta,old,bad,hashes)
        bad=copy.deepcopy(new);bad['results'][0]['original']='different'
        with self.assertRaises(ValueError):combine(base,full,delta,old,bad,hashes)
        bad=copy.deepcopy(full);bad['window_extents']=[[1,1]]
        with self.assertRaises(ValueError):changed(base,bad)


if __name__=='__main__':unittest.main()
