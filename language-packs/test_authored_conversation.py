import unittest
from authored_conversation import records, protocol


class ConversationExpansionTests(unittest.TestCase):
    def test_scope_and_readings_survive_protocol_export(self):
        values=list(records());cases=protocol(values)['samples']
        self.assertEqual(len({(v['source_language'],v['target_language']) for v in values}),90)
        for record,case in zip(values,cases):
            if case['target'] in ('ar','zh','ja','ko'): self.assertTrue(case['expected_reading'])
            text=case['original'].encode('utf-16-le')
            self.assertEqual(text[case['start']*2:case['end']*2].decode('utf-16-le'),record['source'])

    def test_articles_and_possession_are_not_copied_into_focus(self):
        values=list(records())
        price=next(v for v in values if v['logical_id'].endswith('conversation_price:en-ar'))
        self.assertEqual(price['target'],'سعر')
        self.assertEqual(price['target_context'][:price['target_span'][0]],'ال')
        self.assertFalse(any('conversation_family:' in v['logical_id'] and 'ar' in
            (v['source_language'],v['target_language']) for v in values))
        self.assertTrue(all('context_pattern' not in v['usage'] for v in values))


if __name__=='__main__': unittest.main()
