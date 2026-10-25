import unittest
from conversation_priority import partition_sms_records, tokenize
from expand_conversation_contexts import focus_matches
from prepare_sms_probe import first_word, prepare
from capture_phrase_matrix import convert
import hashlib


class PriorityTests(unittest.TestCase):
    def test_same_contributor_across_languages_and_duplicate_purge(self):
        identifiers=[str(i) for i in range(1,100)]
        reserved=next(x for x in identifiers if int.from_bytes(hashlib.sha256(('vipi-nus-contributor-v2:'+x).encode()).digest()[:8],'big')%100<15)
        train=next(x for x in identifiers if int.from_bytes(hashlib.sha256(('vipi-nus-contributor-v2:'+x).encode()).digest()[:8],'big')%100>=15)
        rows=[('en','1','Okay',train),('en','2','Okay',reserved),('zh','3','明天见',reserved),
              ('en','4','A new sentence',reserved),('en','5','A new sentence',reserved)]
        development,report=partition_sms_records(rows)
        self.assertEqual(development,[('en','Okay')])
        self.assertEqual(report['partitions']['en:excluded_cross_partition_duplicate'],1)
        self.assertEqual(report['partitions']['en:excluded_reserved_duplicate'],1)
        self.assertEqual(report['partitions']['zh:reserved'],1)
        self.assertEqual(report['reserved_unique_texts'],2)

    def test_unicode_offsets_and_repeated_focus_are_not_guessed(self):
        forms={'book':{('book','','reading material')}}
        self.assertEqual(focus_matches('📖 A book.','en',forms)['book'][1:3],(4,8))
        self.assertFalse(focus_matches('bookcase','en',forms))
        self.assertFalse(focus_matches('book and book','en',forms))
        self.assertIn('咖啡',list(tokenize('我想喝咖啡。','zh')))

    def test_sms_probe_keeps_reserved_sources_without_references(self):
        rows=[('en','1','Private development','development'),('en','2','📖 A book.','reserved'),
              ('en','3','😂','reserved'),('zh','4','我在家。','reserved')]
        cases,samples,counts=prepare(rows,1)
        self.assertEqual(len(cases),2);self.assertEqual(len(samples),18)
        self.assertTrue(all(len(c['text'])==1 for c in cases))
        self.assertFalse(any('expected_target' in s for s in samples))
        self.assertEqual(first_word('📖 A book.','en'),(3,4,'A'))
        self.assertEqual(counts['en:excluded_no_word'],1)
        self.assertEqual(prepare(list(reversed(rows)),1),prepare(rows,1))

    def test_capture_adapter_rejects_duplicates_and_wrong_protocol(self):
        corpus={'cases':[{'id':'a','text':{'en':'A book.'}}],'expected_pairs':1}
        protocol={'samples':[{'source':'en','target':'es','case':'a','original':'A book.'}]}
        row={**protocol['samples'][0],'status':'executed','translation':'Un libro.'}
        capture={'complete':True,'cases_expected':1,'cases_completed':1,'protocol_sha256':'sha','results':[row]}
        self.assertEqual(convert(corpus,protocol,capture,'sha')[0]['samples'][0]['translation'],'Un libro.')
        with self.assertRaises(ValueError):convert(corpus,protocol,capture,'wrong')
        with self.assertRaises(ValueError):convert(corpus,protocol,{**capture,'cases_completed':2,'results':[row,row]},'sha')


if __name__=='__main__':unittest.main()
