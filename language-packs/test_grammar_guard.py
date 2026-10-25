import unittest
from build_grammar_guard import collect, collect_redirects, inherit_redirects
from build_wiktextract import LANGUAGES


class GrammarGuardTests(unittest.TestCase):
    def test_native_function_word_and_auxiliary_inflections_are_retained(self):
        terms = {language: {} for language in LANGUAGES}
        collect({"lang_code": "en", "word": "up", "pos": "prep"}, 1, terms)
        collect({"lang_code": "en", "word": "up", "pos": "verb"}, 2, terms)
        collect({"lang_code": "en", "word": "be", "pos": "verb", "senses": [{"tags": ["auxiliary"]}],
                 "forms": [{"form": "is"}, {"form": "are"}]}, 3, terms)
        collect({"lang_code": "ja", "word": "は", "pos": "particle", "forms": [{"form": "wa", "tags": ["romanization"]}]}, 4, terms)
        collect({"lang_code": "en", "word": "coffee", "pos": "noun"}, 5, terms)
        self.assertEqual(set(terms["en"]), {"up", "be", "is", "are"})
        self.assertEqual(set(terms["ja"]), {"は"})
        self.assertEqual(terms["en"]["up"]["line"], 1)

    def test_native_character_category_and_simplified_redirect_inherit_evidence(self):
        terms = {language: {} for language in LANGUAGES}
        redirects = {language: {} for language in LANGUAGES}
        # Shapes observed in the pinned dictionary, including pos=character
        # and a simplified form with no part-of-speech/gloss of its own.
        collect({"lang_code": "zh", "word": "嗎", "pos": "character",
                 "senses": [{"categories": ["Chinese particles"]}]}, 58847, terms)
        collect_redirects({"lang_code": "zh", "word": "吗", "pos": "character",
                           "redirects": ["嗎"]}, 56436, redirects)
        self.assertEqual(inherit_redirects(terms, redirects), {"zh": 1})
        self.assertEqual(terms["zh"]["嗎"]["reason"], "native_category:Chinese particles")
        self.assertEqual(terms["zh"]["吗"]["target"], "嗎")
        self.assertEqual(terms["zh"]["吗"]["line"], 56436)

    def test_redirect_cycles_and_foreign_categories_do_not_invent_grammar(self):
        terms = {language: {} for language in LANGUAGES}
        redirects = {language: {} for language in LANGUAGES}
        collect({"lang_code": "en", "word": "coffee", "pos": "noun",
                 "categories": ["Chinese particles", "English terms derived from pronouns"]}, 1, terms)
        for word, target in [("a", "b"), ("b", "a")]:
            collect_redirects({"lang_code": "en", "word": word, "redirects": [target]}, 2, redirects)
        self.assertEqual(inherit_redirects(terms, redirects), {})
        self.assertFalse(terms["en"])
        collect({"lang_code": "en", "word": "a", "pos": "article"}, 3, terms)
        self.assertEqual(inherit_redirects(terms, redirects), {"en": 1})
        self.assertEqual(set(terms["en"]), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
