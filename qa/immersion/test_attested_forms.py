import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from build_attested_forms import build
from conversation_corpus import sha_file


class AttestedFormTests(unittest.TestCase):
    def test_ambiguous_analyses_and_nonatomic_lemmas_remain_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'sources';folder=source/'fixture';folder.mkdir(parents=True)
            corpus=''
            for number in range(5):
                corpus+=f'# sent_id = example-{number}\n'+'''1\tsaw\tsee\tVERB\t_\tTense=Past\t0\troot\t_\t_
2\tsaw\tsaw\tNOUN\t_\tNumber=Sing\t1\tobj\t_\t_
3\thouses\thouse\tNOUN\t_\tNumber=Plur\t1\tobj\t_\t_
4\t책을\t책+을\tNOUN\t_\t_\t1\tobj\t_\t_
5\tcan\tcan\tAUX\t_\tVerbForm=Fin\t1\taux\t_\t_
6\tcan\tcan\tNOUN\t_\tNumber=Sing\t1\tobj\t_\t_
7\thouses\t_\tX\t_\t_\t1\tdep\t_\t_

'''
            (folder/'train.conllu').write_text(corpus)
            (folder/'README.md').write_text('License: CC BY-SA 4.0\nGenre: synthetic fixture\n')
            (folder/'receipt.json').write_text(json.dumps({'commit':'fixture','assets':[
                {'file':name,'sha256':sha_file(folder/name)} for name in ('train.conllu','README.md')]}))
            sources=[('en','fixture','fixture','train.conllu')];output=root/'first'
            receipt=build(source,output,sources)
            self.assertFalse(receipt['linguistic_acceptance'])
            self.assertEqual(receipt['languages'][0]['ambiguous_surfaces'],1)
            with sqlite3.connect(output/'attested-forms.sqlite') as db:
                rows=db.execute('SELECT lemma,pos,occurrences,evidence FROM analyses WHERE source_key=? ORDER BY lemma',('saw',)).fetchall()
                self.assertEqual([(r[0],r[1],r[2]) for r in rows],[('saw','NOUN',5),('see','VERB',5)])
                self.assertTrue(all(len(json.loads(r[3]))==3 for r in rows))
                self.assertEqual(db.execute('SELECT atomic_lemma_candidate FROM analyses WHERE surface=?',('책을',)).fetchone()[0],0)
                self.assertEqual(json.loads(db.execute('SELECT features FROM analyses WHERE surface=?',('houses',)).fetchone()[0]),{'Number':'Plur'})
            with self.assertRaises(FileExistsError):build(source,output,sources)
            complete=build(source,root/'all-pos',sources,all_parts=True)
            self.assertEqual(complete['analysis_scope'],'all_observed_ud_parts_of_speech')
            with sqlite3.connect(root/'all-pos'/'attested-forms.sqlite') as db:
                self.assertEqual(db.execute('SELECT pos FROM analyses WHERE source_key=? ORDER BY pos',('can',)).fetchall(),[('AUX',),('NOUN',)])
                self.assertEqual(db.execute('SELECT atomic_lemma_candidate FROM analyses WHERE lemma=?',('_',)).fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM analyses WHERE source_key=?',('houses',)).fetchone()[0],2)
            (folder/'train.conllu').write_text(corpus+'# changed\n')
            with self.assertRaisesRegex(ValueError,'Changed source'):build(source,root/'changed',sources)


if __name__=='__main__':unittest.main()
