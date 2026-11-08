"""Structural phrase-extraction controls; not bilingual meaning claims."""
import unittest
from extract_phrases import consistent_targets, lexical_score


class PhraseExtractionTests(unittest.TestCase):
    def test_one_word_can_recover_complete_unaligned_target_modifier(self):
        # The shorter variant remains visible; expansion is not semantic approval.
        self.assertEqual(set(consistent_targets(0,1,['computadora','portátil'],{(0,0)})),{(0,1,0,1),(0,2,0,1)})

    def test_left_and_right_unaligned_words_are_both_retained(self):
        self.assertEqual(set(consistent_targets(1,2,['el','correo','electrónico'],{(1,1)})),{(1,2,1,2),(0,2,1,2),(1,3,1,2),(0,3,1,2)})

    def test_external_alignment_rejects_crossing_interval(self):
        self.assertEqual(consistent_targets(0,1,['a','b','c'],{(0,0),(0,2),(1,1)}),[])

    def test_alignment_outside_boundary_blocks_expansion(self):
        self.assertEqual(consistent_targets(0,1,['a','b'],{(0,0),(1,1)}),[(0,1,0,1)])

    def test_empty_alignment_does_not_create_phrase(self):
        self.assertEqual(consistent_targets(0,1,['a','b'],set()),[])

    def test_many_to_one_phrase_requires_complete_source_scope(self):
        links={(0,0),(1,0)}
        self.assertEqual(consistent_targets(0,1,['target'],links),[])
        self.assertEqual(consistent_targets(0,2,['target'],links),[(0,1,0,1)])

    def test_sentence_boundary_cannot_expand_into_next_sentence(self):
        self.assertEqual(set(consistent_targets(0,1,['one','.','two'],{(0,0)})),{(0,1,0,1),(0,2,0,1)})

    def test_target_cap_retains_only_fitting_variants(self):
        self.assertEqual(consistent_targets(0,1,['a','b','c'],{(0,1)},maximum=1),[(1,2,1,2)])

    def test_bidirectional_scoring_uses_reverse_conditioning(self):
        import math
        score,missing=lexical_score(['water'],['agua'],{(0,0)}, {('water','agua'):math.log(.8)}, {('agua','water'):math.log(.5)})
        self.assertAlmostEqual(score,(math.log(.8)+math.log(.5))/2)
        self.assertEqual(missing,0)

    def test_dictionary_complete_form_uses_utf16_not_codepoints(self):
        import sqlite3
        from corroborate_units import complete_units
        db=sqlite3.connect(':memory:')
        db.executescript('''CREATE TABLE surfaces(normalized,lexeme,surface,start,end,number,mode,features);
          CREATE TABLE lexemes(id,headword,pos,source_safe,target_safe,source_url);
          CREATE TABLE terms(lexeme,sense,reading,eligible,qualifiers);
          CREATE TABLE senses(id,label,explicit,source_url);''')
        for lid,end in [(1,4),(2,3)]:
            db.execute('INSERT INTO surfaces VALUES(?,?,?,?,?,?,?,?)',('a😀b',lid,'a😀b',0,end,0,1,'[]'))
            db.execute('INSERT INTO lexemes VALUES(?,?,?,?,?,?)',(lid,'a😀b','noun',1,1,'structural-test'))
        result=complete_units(db,'a😀b')
        self.assertEqual([row['lexeme_id'] for row in result],[1])
        db.close()


if __name__ == '__main__':
    unittest.main()
