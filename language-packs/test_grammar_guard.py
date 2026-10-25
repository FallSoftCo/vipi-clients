import unittest
from build_grammar_guard import collect
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


if __name__ == "__main__":
    unittest.main()
