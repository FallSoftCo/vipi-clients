import unittest
from authored_people_ideas_units import records


class PeopleIdeasUnitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=list(records())

    def test_plural_children_cannot_borrow_singular_swahili(self):
        rows=[r for r in self.rows if r['source_language']=='en' and r['target_language']=='sw' and r['source']=='children']
        self.assertTrue(rows)
        self.assertEqual({r['target'].casefold() for r in rows},{'watoto'})
        reverse=[r for r in self.rows if r['source_language']=='sw' and r['target_language']=='en' and r['source']=='mtoto']
        self.assertEqual({r['target'].casefold() for r in reverse},{'child'})

    def test_negative_pronoun_and_arabic_conjunction_are_not_approved_nouns(self):
        for language,word in [('fr','personne'),('ar','أم'),('ar','عالم')]:
            self.assertFalse(any(r['source_language']==language and r['source'].casefold()==word for r in self.rows))
        self.assertTrue(any(r['target_language']=='ar' and r['target']=='أم' for r in self.rows))
        self.assertTrue(any(r['source_language']=='fr' and r['source']=='personnes' for r in self.rows))

    def test_lexical_carriers_cannot_become_whole_message_shortcuts(self):
        self.assertTrue(all(r['usage']['whole_reference'] is False for r in self.rows))
        for row in self.rows:
            if row['target_language'] in ('ar','zh','ja','ko'):
                self.assertTrue(row['reading'])
