import unittest
from adjective_agreement import whole_form
from build_lexical_shards import surface

class AttestedAdjectiveAgreement(unittest.TestCase):
    def test_supplied_positive_agreement(self):
        self.assertEqual(surface("alérgico","alérgica","adj",["feminine","form-of","singular"],"es"),(0,8,0,2))
        self.assertEqual(surface("heureux","heureuses","adj",["feminine","plural"],"fr"),(0,9,0,2))
        self.assertEqual(surface("buono","buone","adj",["feminine","plural"],"it"),(0,5,0,2))
        self.assertEqual(surface("cansado","cansadas","adj",["feminine","plural"],"pt"),(0,8,0,2))
    def test_degree_and_verbal_features_do_not_become_agreement(self):
        for tags in [["comparative","feminine"],["superlative","plural"],
                     ["participle","feminine"],["past","plural"],["archaic","feminine"]]:
            self.assertIsNone(whole_form("bueno","mejores","adj",tags,"es"))
    def test_unknown_features_and_other_languages_are_not_guessed(self):
        self.assertIsNone(whole_form("gut","gute","adj",["feminine"],"de"))
        self.assertIsNone(whole_form("alérgico","alérgica","adj",[],"es"))
        self.assertIsNone(whole_form("alérgico","alérgica","noun",["feminine"],"es"))
        self.assertIsNone(whole_form("fácil","más fácil","adj",["feminine"],"es"))
    def test_noun_and_verb_contracts_are_unchanged(self):
        self.assertEqual(surface("libro","libros","noun",["plural"],"es"),(0,6,2,2))
        self.assertEqual(surface("tener","tengo","verb",["first-person","present","singular"],"es"),(0,0,0,0))

if __name__=="__main__":unittest.main()
