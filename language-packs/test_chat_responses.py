import unittest
import authored_chat_responses as author

class ChatResponsesTests(unittest.TestCase):
    def test_swahili_short_replies_and_written_aliases(self):
        rows=list(author.records())
        for source,target,left,right in [('sw','en','ndio','Yes.'),('sw','en','Ndiyo.','Yes.'),
                ('sw','en','Hapana','No.'),('sw','en','sawa','Okay.'),('en','sw','OK','Sawa.'),
                ('en','sw','Please.','Tafadhali.')]:
            self.assertTrue(any((r['source_language'],r['target_language'],r['source_context'],r['target_context'])==
                (source,target,left,right) for r in rows),(source,target,left))

    def test_context_dependent_responses_are_omitted(self):
        for row in author.records():
            topic=row['logical_id'].split(':')[1].removeprefix('chat_response_')
            for side in ('source','target'):
                self.assertNotIn((topic,row[side+'_language']),author.OMITTED)
                self.assertFalse(topic=='please' and row[side+'_language']=='ko')
            self.assertEqual([{'focus':row['source']}],row['usage']['source_frame_pattern'])
            self.assertEqual([{'focus':row['target']}],row['usage']['target_frame_pattern'])

    def test_readings_cover_every_admitted_non_roman_sentence(self):
        rows=list(author.records());readings={(r['language'],r['text']):r['latin'] for r in author.readings()}
        self.assertEqual(len(rows),len({r['logical_id'] for r in rows}))
        self.assertEqual(13,len(readings))
        self.assertEqual(110,len({(r['source_language'],r['target_language']) for r in rows}))
        for row in rows:
            self.assertTrue(row['usage']['whole_reference'])
            if row['target_language'] in ('ar','zh','ja','ko'):
                self.assertIn((row['target_language'],row['target_context']),readings)
                self.assertTrue(row['reading'])

if __name__=='__main__':unittest.main()
