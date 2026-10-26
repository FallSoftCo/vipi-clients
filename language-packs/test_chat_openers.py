import unittest
from authored_chat_openers import formula, readings, records, source_forms


class ChatOpenersTests(unittest.TestCase):
    def test_sentence_question_punctuation_does_not_erase_reading(self):
        self.assertEqual(formula('最近どう？~Saikin dō?'), ('最近どう？','Saikin dō?'))
        with self.assertRaises(ValueError): formula('最近どう？~最近どう？')
        values=readings()
        self.assertEqual(len(values),20)
        self.assertEqual(sum(row['latin'].endswith('?') for row in values),4)

    def test_every_non_roman_target_has_a_reading_and_complete_formula_scope(self):
        values=list(records())
        self.assertEqual(len({(r['source_language'],r['target_language']) for r in values}),110)
        for row in values:
            if row['target_language'] in ('ar','zh','ja','ko'): self.assertTrue(row['reading'])
            self.assertEqual(row['usage']['context_extent'],'local_phrase')
            self.assertTrue(row['usage']['lexical_unit'])
            self.assertEqual(row['usage']['source_frame_pattern'],[{'focus':row['source']}])
            self.assertEqual(row['usage']['target_frame_pattern'],[{'focus':row['target']}])

    def test_namesake_and_short_aliases_are_explicit(self):
        self.assertIn('mambo vipi',source_forms('whats_up','sw','Mambo vipi?'))
        self.assertIn('hi',source_forms('hello','en','Hello.'))
        self.assertNotIn('hello Alex',source_forms('hello','en','Hello.'))
