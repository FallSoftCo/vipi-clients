import unittest,json
from present_verb_forms import variants,finite_people
class PresentForms(unittest.TestCase):
    def forms(self,head,rows,language):
        return list(variants(head,[(word,json.dumps(tags.split())) for word,tags in rows],language))
    def test_english_head_classification_and_syncretic_past(self):
        self.assertEqual([r["written"] for r in self.forms("play",[("plays","present singular third-person"),("played","past")],"en")],["play","plays"])
        self.assertEqual(self.forms("read",[("read","past"),("read","present singular first-person")],"en"),[])
        self.assertEqual(self.forms("be",[],"en"),[])
    def test_no_imperative_participle_or_negative_invented_form(self):
        rows=[("trabajo","present indicative singular first-person"),("trabaje","present subjunctive singular first-person"),
            ("trabajad","imperative plural second-person"),("trabajando","present participle"),("trabajo","negative")]
        got=self.forms("trabajar",rows,"es")
        self.assertEqual([r["written"] for r in got],["trabajo"])
        self.assertEqual(got[0]["supplied"][0]["index"],0)
    def test_spanish_shared_past_is_withheld(self):
        self.assertEqual(self.forms("trabajar",[("trabajamos","present indicative plural first-person"),("trabajamos","preterite indicative plural first-person")],"es"),[])
    def test_subject_and_person_including_unicode_offsets(self):
        f={"present-person-1s","present-person-3s"}
        self.assertEqual(finite_people(f,"😀 I work",5,"en"),{"1s"})
        self.assertEqual(finite_people(f,"She works",4,"en"),{"3s"})
        self.assertEqual(finite_people(f,"I can work",6,"en"),set())
        self.assertEqual(finite_people(f,"J’écris",2,"fr"),{"1s"})
        self.assertEqual(finite_people(f,"Elle écrit",5,"fr"),{"3s"})
        self.assertEqual(finite_people(f,"Tu trabajo",3,"es"),set()) # unaccented Tu supplies possessive/noun evidence
    def test_incompatible_explicit_subject_withholds(self):
        self.assertEqual(finite_people({"present-person-1s"},"He work",3,"en"),set())
        self.assertEqual(finite_people({"present-person-1s"},"Ella trabajo",5,"es"),set())
        self.assertEqual(finite_people({"present-person-1s"},"Ich arbeite",4,"de"),{"1s"})
    def test_auxiliary_questions_are_not_positive_present_assertions(self):
        for text in ["Did I live here?", "Will I live here?", "Can I live here?", "Could I live here?", "Have I live here?"]:
            with self.subTest(text=text):
                self.assertEqual(finite_people({"present-person-1s"},text,text.index("live"),"en"),set())
        self.assertEqual(finite_people({"present-person-1s"},"Do I live here?",5,"en"),{"1s"})
        self.assertEqual(finite_people({"present-person-1s"},"I live here.",2,"en"),{"1s"})
    def test_no_accent_or_internal_space_rewriting(self):
        self.assertEqual(self.forms("trabajar",[("yo trabajo","present indicative singular first-person")],"es"),[])
        with self.assertRaises(AssertionError):self.forms("lavorare",[("lavóra","present indicative singular third-person")],"it")
if __name__=="__main__":unittest.main()
