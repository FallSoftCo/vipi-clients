import json,unittest
from add_attested_past_verbs import variants,source_class
class AttestedPastVerbs(unittest.TestCase):
    def test_exact_reading_and_past_only(self):
        rows=[(1,'食べました','tabemashita','["past","polite"]'),
              (2,'食べませんでした','tabemasendeshita','["past","negative","polite"]'),
              (3,'食べさせた','tabesaseta','["past","causative"]'),
              (4,'食べたら','tabetara','["past","conditional"]'),
              (5,'食べます','tabemasu','["polite"]')]
        result=list(variants('食べる',rows,'ja'))
        self.assertEqual([r['written'] for r in result],['食べました'])
        self.assertEqual(result[0]['reading'],'tabemashita')
        self.assertIn('past-source-unambiguous',result[0]['features'])
    def test_missing_polite_past_label_requires_both_supplied_forms_and_readings(self):
        pair=[(1,'行きます','ikimasu','["polite"]'),(2,'行きました','ikimashita','["polite"]')]
        result=list(variants('行く',pair,'ja'))
        self.assertEqual([r['written'] for r in result],['行きました'])
        self.assertEqual(result[0]['supplied'][0]['tags'],['polite'])
        self.assertIn('japanese-supplied-polite-past-1',result[0]['features'])
        self.assertEqual(list(variants('行く',pair[1:],'ja')),[])
        wrong=[pair[0],(2,'行きました','yukimashita','["polite"]')]
        self.assertEqual(list(variants('行く',wrong,'ja')),[])
    def test_syncretism_and_participles_are_not_asserted_finite(self):
        self.assertEqual(source_class('buy','bought',[{'past'},{'past','participle'}],'en'),'past-source-requires-finite-clause')
        self.assertEqual(source_class('read','read',[{'past'},{'present'}],'en'),'past-source-syncretic')
        self.assertEqual(source_class('go','went',[{'past'},{'past','subjunctive'}],'en'),'past-source-unambiguous')
    def test_missing_and_competing_readings_withhold(self):
        for readings in [('',),('tabeta','tabetta')]:
            rows=[(i,'食べた',r,'["past"]') for i,r in enumerate(readings)]
            self.assertEqual(list(variants('食べる',rows,'ja')),[])
    def test_korean_shared_statement_question_spelling_keeps_past(self):
        rows=[(1,'먹었어요','meogeosseoyo','["past","indicative","informal","polite"]'),
              (2,'먹었어요','meogeosseoyo','["past","interrogative","informal","polite"]'),
              (3,'먹었습니까','meogeotseumnikka','["past","interrogative","formal","polite"]')]
        result=list(variants('먹다',rows,'ko'))
        self.assertEqual([r['written'] for r in result],['먹었어요'])
        self.assertIn('past-source-unambiguous',result[0]['features'])
if __name__=='__main__':unittest.main()
