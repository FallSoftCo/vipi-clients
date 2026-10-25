import copy
import unittest

from authored_everyday import records
from context_patterns import match_pattern,validate_pattern


class ContextPatternTests(unittest.TestCase):
    def test_authored_patterns_preserve_each_possessor_and_both_numbers(self):
        patterns=[x for x in records() if 'context_pattern' in x['usage']]
        self.assertEqual(len(patterns),3)
        for row in patterns:
            validate_pattern(row)
            for subject in ('you','they','we'):
                for possessor in ('my','your','their','our'):
                    text=f'Can {subject} bring {possessor} {row["source"]}?'
                    focus=match_pattern(text,row['usage']['context_pattern'])
                    self.assertIsNotNone(focus)
                    actual=text[:focus[0]]+row['target']+text[focus[1]:]
                    self.assertEqual(actual,f'Can {subject} bring {possessor} {row["target"]}?')

    def test_pattern_cannot_silently_expand_focus_into_possessor(self):
        row=next(x for x in records() if 'context_pattern' in x['usage'])
        changed=copy.deepcopy(row)
        changed['usage']['context_pattern']=[{'literal':'Can you bring '},{'focus':'my book'},{'literal':'?'}]
        with self.assertRaises(ValueError): validate_pattern(changed)

    def test_unlisted_context_and_ambiguous_focus_do_not_match(self):
        row=next(x for x in records() if 'context_pattern' in x['usage'])
        self.assertIsNone(match_pattern('Can you bring her book?',row['usage']['context_pattern']))
        self.assertIsNone(match_pattern('xaaaa',[{'literal':'x'},{'slot':['a','aa']},{'focus':'a'},{'slot':['a','aa']}]))

    def test_open_ended_empty_and_oversized_slots_reject(self):
        for slot in ('anything',[],[''],['x']*33):
            with self.assertRaises(ValueError): match_pattern('Can you bring my book?',[
                {'literal':'Can '},{'slot':slot},{'focus':'book'}])

    def test_arabic_object_ending_stays_outside_lexical_focus(self):
        rows=[x for x in records() if x['target_language']=='ar' and x['source_language']=='en']
        by_word={x['source']:x for x in rows}
        for word, sentence, focus in [('bread','أريد خبزًا.','خبز'),('tea','أريد شايًا.','شاي')]:
            row=by_word[word]
            self.assertEqual(row['target_context'],sentence)
            self.assertEqual(sentence[slice(*row['target_span'])],focus)
            self.assertEqual(sentence[row['target_span'][1]:],'ًا.')


if __name__=='__main__': unittest.main()
