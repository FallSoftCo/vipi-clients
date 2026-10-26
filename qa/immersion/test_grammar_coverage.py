import argparse
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import grammar_coverage as audit
from conversation_corpus import sha_file


class GrammarCoverageTests(unittest.TestCase):
    def test_compiled_pair_inventory_and_inflections_remain_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'sources';folder=source/'fixture';folder.mkdir(parents=True)
            # Synthetic CoNLL-U, including a multiword surface and an empty
            # syntactic node that must not become additional content tokens.
            corpus='''# sent_id = one
1\tMeine\tmein\tDET\t_\tPoss=Yes\t2\tdet:poss\t_\t_
2\tHäuser\tHaus\tNOUN\t_\tNumber=Plur\t3\tnsubj\t_\t_
3\tstehen\tstehen\tVERB\t_\tTense=Pres\t0\troot\t_\t_
4-5\tzur\t_\t_\t_\t_\t_\t_\t_\t_
4\tzu\tzu\tADP\t_\t_\t6\tcase\t_\t_
5\tder\tder\tDET\t_\t_\t6\tdet\t_\t_
6\tStraße\tStraße\tNOUN\t_\t_\t3\tobl\t_\t_
7\t.\t.\tPUNCT\t_\t_\t3\tpunct\t_\t_

# sent_id = two
1\tAnna\tAnna\tPROPN\t_\t_\t2\tnsubj\t_\t_
2\tging\tgehen\tVERB\t_\tTense=Past\t0\troot\t_\t_
2.1\tgeht\tgehen\tVERB\t_\t_\t_\t_\t_\t_
3\t?\t?\tPUNCT\t_\t_\t2\tpunct\t_\t_

'''
            (folder/'train.conllu').write_text(corpus)
            (folder/'README.md').write_text('License: CC BY-SA 4.0\nGenre: synthetic test fixture\nFeatures: synthetic\n')
            (folder/'receipt.json').write_text(json.dumps({'commit':'fixture-revision','assets':[
                {'file':name,'sha256':sha_file(folder/name)} for name in ('train.conllu','README.md')]}))
            catalog=root/'catalog.sqlite'
            with sqlite3.connect(catalog) as db:
                db.execute('CREATE TABLE revisions(source_key TEXT,source_language TEXT)')
                db.execute('INSERT INTO revisions VALUES (?,?)',('stehen','de'))
            packs=root/'packs';packs.mkdir()
            for target in ['en','es','fr','it','pt','ar','zh','ja','ko']:
                path=packs/('de-'+target);path.mkdir();database=path/'vocabulary.sqlite'
                with sqlite3.connect(database) as db:
                    db.execute('CREATE TABLE vocabulary(source TEXT)')
                    db.executemany('INSERT INTO vocabulary VALUES (?)',[(s,) for s in ['haus','gehen','stehen']+([] if target=='es' else ['straße'])])
                (path/'manifest.json').write_text(json.dumps({'source_language':'de','target_language':target,
                    'sha256':sha_file(database),'revision':7}))
            args=argparse.Namespace(source=source,catalog=catalog,packs=packs,output=root/'report.json')
            with patch.object(audit,'SOURCES',[('de','fixture','fixture-revision','train.conllu')]),contextlib.redirect_stdout(io.StringIO()):
                audit.main(args)
                with self.assertRaises(ValueError):audit.main(args)
            row=json.loads(args.output.read_text())['languages'][0]
            self.assertEqual(row['counts']['syntactic_tokens'],10)
            self.assertEqual(row['counts']['content_tokens'],4)
            self.assertEqual(row['counts']['recognized_content_surfaces'],1)
            pairs={p['target']:p for p in row['native_pack_source_recognition']}
            self.assertEqual(pairs['en']['recognized_content_surfaces'],2)
            self.assertEqual(pairs['es']['recognized_content_surfaces'],1)
            self.assertEqual(pairs['en']['unrecognized_surface_with_known_lemma'],2)
            self.assertEqual(row['sentences_by_annotated_phenomenon'],{'possession_annotation':1,
                'plural_annotation':1,'past_tense_annotation':1,'proper_name':1,'question_punctuation':1})


if __name__=='__main__':unittest.main()
