import unittest
from conversation_corpus import key
from prepare_xpersona_probe import choose,rank,utterances


class XPersonaTests(unittest.TestCase):
    def test_training_duplicates_markers_and_reversed_views_do_not_fill_probe(self):
        rows=[{'dialogue':[['__SILENCE__','Hello there.'],['I have a cat.','I have a dog.']]},
              {'dialogue':[['I have a dog.','I have a cat.'],['Hello there.','__SILENCE__']]},
              {'dialogue':[['Read this book.','2345']]},
              {'dialogue':[['Read this book.','x'*281]]}]
        selected,counts=choose('en',rows,{key('Hello there.')},2)
        self.assertIn(0,{r[1] for r in selected});self.assertNotIn(1,{r[1] for r in selected})
        self.assertEqual(counts['duplicate_full_dialogue_views'],1)
        self.assertEqual(len({key(r[3]) for r in selected}),2)
        with self.assertRaises(ValueError):choose('en',rows,{key('Hello there.')},3)
        with self.assertRaises(ValueError):list(utterances({'dialogue':[['one']]}))

    def test_longer_dialogue_cannot_improve_its_rank(self):
        rows=[{'dialogue':[[f'A different question {i}.',f'Another response {i}.']]} for i in range(20)]
        chosen,_=choose('en',rows,set(),4);expected=sorted(range(20),key=lambda i:(rank('en',i),i))[:4]
        self.assertEqual([r[1] for r in chosen],expected)
        for i,row in enumerate(rows):
            if i not in expected:row['dialogue'] += [[f'Extra unique turn {i} {j}.',f'Extra answer {i} {j}.'] for j in range(50)]
        self.assertEqual([r[1] for r in choose('en',rows,set(),4)[0]],expected)


if __name__=='__main__':unittest.main()
