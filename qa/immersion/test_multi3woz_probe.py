import unittest
from conversation_corpus import key
from prepare_multi3woz_probe import choose,is_user,dialogue_fingerprint


class DialogueProbeTests(unittest.TestCase):
    def test_selection_excludes_training_duplicates_and_multiple_turns(self):
        rows=[('a',0,'Bonjour.'),('a',2,'Je cherche un hôtel.'),('b',0,'Texte déjà vu.'),
              ('c',0,'Une autre question.'),('d',0,'1234'),('e',0,'x'*281)]
        selected,counts=choose('fr',rows,{key('Texte déjà vu.')},2)
        self.assertEqual({r[1] for r in selected},{'a','c'})
        self.assertEqual(len(selected),2)
        self.assertEqual(counts['excluded_train_dev_duplicate'],1)
        self.assertEqual(counts['excluded_no_word'],1)
        self.assertEqual(counts['excluded_length'],1)
        self.assertEqual(choose('fr',list(reversed(rows)),{key('Texte déjà vu.')},2)[0],selected)
        with self.assertRaises(ValueError):choose('fr',rows,{key('Texte déjà vu.')},3)

    def test_explicit_speaker_does_not_assume_perfect_alternation(self):
        self.assertFalse(is_user({'speaker':'SYSTEM','metadata':{'hotel':{}}}))
        self.assertTrue(is_user({'speaker':'USER','metadata':{}}))
        with self.assertRaises(ValueError):is_user({'speaker':'ASSISTANT','metadata':{}})
        with self.assertRaises(ValueError):is_user({'speaker':'USER','metadata':{'hotel':{}}})

    def test_dialogue_rank_is_independent_of_number_of_turns(self):
        ids=['dialogue-'+str(i) for i in range(30)]
        expected=sorted(ids,key=lambda d:dialogue_fingerprint('fr',d))[:5]
        rows=[(d,0,'Je cherche un hôtel '+d+'.') for d in ids]
        selected,_=choose('fr',rows,set(),5)
        self.assertEqual([r[1] for r in selected],expected)
        expanded=rows+[(d,i,'Une question différente '+d+' '+str(i)+'.')
            for d in ids if d not in expected for i in range(1,80)]
        selected,_=choose('fr',expanded,set(),5)
        self.assertEqual([r[1] for r in selected],expected)


if __name__=='__main__':unittest.main()
