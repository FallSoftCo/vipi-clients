import unittest
import authored_chat_response_aliases as aliases

class ChatResponseAliasesTests(unittest.TestCase):
    def test_reverse_written_aliases_are_lexical_only(self):
        rows=list(aliases.records())
        for source,target,left,right in [('en','sw','Yes','ndio'),('en','sw','Okay','sawa'),('sw','en','Sawa','OK')]:
            matches=[r for r in rows if (r['source_language'],r['target_language'],r['source'],r['target'])==(source,target,left,right)]
            self.assertTrue(matches,(source,target,left,right))
            self.assertTrue(all(r['usage']['whole_reference'] is False for r in matches))

    def test_new_whole_references_use_only_explicit_uppercase_source(self):
        rows=list(aliases.records())
        self.assertEqual(len(rows),len({r['logical_id'] for r in rows}))
        for row in rows:
            if row['usage']['whole_reference']:
                self.assertEqual(row['source_context'],row['source_context'].upper())
                self.assertIn(row['source_language'],aliases.ROMAN)
        self.assertTrue(any(r['source_context']=='NDIO' and r['target_context']=='Yes.' and r['usage']['whole_reference'] for r in rows))

if __name__=='__main__':unittest.main()
