import unittest
from noun_carriers import korean,arabic


class NounCarriers(unittest.TestCase):
    def test_korean_final_consonant_changes_only_the_particle(self):
        for head,expected in [("책",{"책은","책이","책을","책과"}),
                              ("커피",{"커피는","커피가","커피를","커피와"})]:
            rows=korean(head,"noun",[])
            self.assertEqual(len(rows),9)
            self.assertTrue(expected <= {r[0] for r in rows})
            for form,start,end,number,_ in rows:
                self.assertEqual(form[start:end],head)
                self.assertEqual(number,0)
                self.assertGreater(len(form),end)
        for head,pos,tags in [("먹다","verb",[]),("서울","name",[]),("ABC","noun",[]),
                              ("책","noun",["archaic"]),("책","noun",["plural"])]:
            self.assertEqual(korean(head,pos,tags),[])

    def test_arabic_requires_supplied_definite_singular_with_same_noun(self):
        rows=arabic("كتاب","الْكِتَابُ","noun",[],["definite","singular","nominative"])
        self.assertEqual(len(rows),1)
        form,start,end,number,_=rows[0]
        self.assertEqual((form,form[start:end],number),("الكتاب","كتاب",0))
        for head,form,pos,head_tags,tags in [
            ("كتاب","الْكُتُب","noun",[],["definite","plural"]),
            ("كتاب","الكتابان","noun",[],["definite","singular","dual"]),
            ("كتاب","الكتاب","noun",[],[]),
            ("كتاب","الكتاب","verb",[],["definite","singular"]),
            ("كتاب","الكتاب","noun",["proper-noun"],["definite","singular"]),
            ("كتاب","الكتابة","noun",[],["definite","singular"]),
            ("الكتاب","الالكتاب","noun",[],["definite","singular"])]:
            self.assertEqual(arabic(head,form,pos,head_tags,tags),[])


if __name__=="__main__":unittest.main()
