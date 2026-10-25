import unittest
from conversation_priority import partition_sms_records, tokenize
from expand_conversation_contexts import focus_matches
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


if __name__=='__main__':unittest.main()
