import unittest
from build_semantic_alternatives import qualify
class AlternativeEvidence(unittest.TestCase):
    def test_synonyms_share_a_relation_without_duplicate_votes(self):
        rows=[]
        for sid in range(1,7):
            head="beber" if sid<=3 else "tomar"
            rows.append((sid,sid+10,head,{"consume-liquid"}))
        rows.append(rows[0])
        got={r["head"]:r for r in qualify(rows)}
        self.assertEqual(set(got),{"beber","tomar"})
        self.assertTrue(all((r["support"],r["total"],r["counterpart_support"])==(6,6,3) for r in got.values()))
    def test_unrelated_meanings_remain_competing(self):
        rows=[(i,i+10,"orilla",{"river-edge"}) for i in range(3)]
        rows.append((4,14,"banco",{"financial-institution"}))
        self.assertEqual(qualify(rows),[])
    def test_unknown_is_not_dropped(self):
        rows=[(i,i+10,"beber",{"consume-liquid"}) for i in range(3)]
        rows.append((4,14,None,set()))
        self.assertEqual(qualify(rows),[])
    def test_conflicting_targets_in_one_sentence_do_not_cast_positive_votes(self):
        rows=[(i,i+10,"orilla",{"river-edge"}) for i in range(3)]
        rows.append((0,20,"banco",{"financial-institution"}))
        self.assertEqual(qualify(rows),[])
    def test_one_sentence_with_many_paraphrases_is_not_three_sources(self):
        self.assertEqual(qualify([(1,10,"beber",{"drink"}),(1,11,"tomar",{"drink"}),(1,12,"beber",{"drink"})]),[])
    def test_rare_counterpart_cannot_borrow_all_synonym_support(self):
        rows=[(i,i+10,"beber",{"drink"}) for i in range(5)]+[(6,16,"tomar",{"drink"})]
        self.assertEqual([r["head"] for r in qualify(rows)],["beber"])
if __name__=="__main__":unittest.main()
