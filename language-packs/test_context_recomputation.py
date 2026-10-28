import argparse,copy,json,shutil,sqlite3,tempfile,unittest
from pathlib import Path
from context_recomputation_proof import verify_recomputation
from build_wiktextract import digest_file

class RecomputedPairEvidence(unittest.TestCase):
    def fixture(self,root):
        languages=['en','es','zh'];before=root/'before';after=root/'after'
        before.mkdir();after.mkdir()
        catalog=dict(inventory_sha256='inventory',release_id='before',shards=[])
        for language in languages:
            path=before/(language+'.sqlite');db=sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE senses(id TEXT,label TEXT);
                CREATE TABLE terms(lexeme INTEGER,sense TEXT);
                CREATE TABLE lemma_links(head TEXT,counterpart TEXT);
                CREATE TABLE surfaces(surface TEXT,lexeme INTEGER);
                CREATE TABLE carrier_evidence(surface TEXT,evidence TEXT);
                CREATE TABLE guards(normalized TEXT,blocked INTEGER,target_blocked INTEGER,protect_inner INTEGER,reason TEXT);
                CREATE TABLE lexemes(id INTEGER,headword TEXT,normalized TEXT,pos TEXT,source_safe INTEGER,target_safe INTEGER,senses INTEGER,source_url TEXT);
                INSERT INTO senses VALUES ('coffee','coffee');
                INSERT INTO terms VALUES (1,'coffee');
                INSERT INTO lexemes VALUES (1,'coffee','coffee','noun',1,1,1,'https://example.test');
                INSERT INTO surfaces VALUES ('coffee',1);
                INSERT INTO guards VALUES ('protected',1,1,1,'identifier');
            """);db.commit();db.close()
            catalog['shards'].append(dict(language=language,sha256=digest_file(path)))
            shutil.copyfile(path,after/path.name)
        current=dict(catalog,release_id='after',changed_languages=['zh'])
        (before/'catalog.json').write_text(json.dumps(catalog));(after/'catalog.json').write_text(json.dumps(current))
        corpus_receipts=[]
        for prefix,release in [('old','before'),('new','after')]:
            paths=[]
            for corpus in ['tatoeba','pgv']:
                row=dict(complete=True,pilot=False,sha256=prefix+corpus,corpus_sha256=corpus,
                    corpus_receipt_sha256='pinned-'+corpus,corpus_partition='development',
                    reserved_sentence_text_read=False,direct_links_only=True,independent_semantic_acceptance=False,
                    source_release_id=release,source_catalog_sha256=digest_file(after/'catalog.json'),
                    changed_pair_languages=['zh'],supplemental_receipts=[],
                    corpus_schema='vipi-pgv-corpus-1' if corpus=='pgv' else 'vipi-conversation-reference-1',
                    automatic_sentence_alignment=corpus=='pgv')
                path=root/(prefix+'-'+corpus+'.json');path.write_text(json.dumps(row));paths.append(path)
            corpus_receipts.append(paths)
        pairs=['en-zh','zh-en','es-zh','zh-es']
        proof=dict(exclusions_sha256='exclusions',base_supplement_receipts=[],policy='disjoint-pinned-source')
        base=dict(source_release_id='before',source_contexts_sha256='oldtatoeba',additional_contexts_sha256=['oldpgv'],disjoint_source_proof=proof)
        delta=dict(source_release_id='after',source_contexts_sha256='newtatoeba',additional_contexts_sha256=['newpgv'],disjoint_source_proof=copy.deepcopy(proof),requested_pairs=pairs)
        args=argparse.Namespace(dictionary_baseline=before/'catalog.json',dictionary_catalog=after/'catalog.json',
            base_context_receipt=corpus_receipts[0],replacement_context_receipt=corpus_receipts[1],base_pair_receipt=[])
        return args,base,delta

    def test_recomputed_scope_keeps_historical_pairs_explicit(self):
        with tempfile.TemporaryDirectory(dir='artifacts') as d:
            root=Path(d);args,base,delta=self.fixture(root);out=root/'proof';out.mkdir()
            result,sha=verify_recomputation(args,base,delta,out)
            self.assertEqual(result['historical_unchanged_pairs'],['en-es','es-en'])
            self.assertEqual(result['replaced_pairs'],sorted(delta['requested_pairs']))
            self.assertFalse(result['semantic_accuracy_claim'])
            self.assertEqual(sha,digest_file(out/'recomputation-proof.json'))

    def test_rejects_missing_empty_pair_dropped_corpus_exclusion_change_and_nonchanged_terms(self):
        for mutation in ['missing-empty-pair','dropped-corpus','changed-exclusion','changed-unchanged-terms','reserved-source']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory(dir='artifacts') as d:
                root=Path(d);args,base,delta=self.fixture(root);out=root/'proof';out.mkdir()
                if mutation=='missing-empty-pair':delta['requested_pairs'].remove('zh-es')
                if mutation=='dropped-corpus':args.replacement_context_receipt.pop()
                if mutation=='changed-exclusion':delta['disjoint_source_proof']['exclusions_sha256']='different'
                if mutation=='reserved-source':
                    path=args.replacement_context_receipt[0];r=json.loads(path.read_text());r['reserved_sentence_text_read']=True;path.write_text(json.dumps(r))
                if mutation=='changed-unchanged-terms':
                    path=args.dictionary_catalog.parent/'en.sqlite';db=sqlite3.connect(path)
                    db.execute("INSERT INTO terms VALUES (1,'new-meaning')");db.commit();db.close()
                    catalog=json.loads(args.dictionary_catalog.read_text())
                    next(r for r in catalog['shards'] if r['language']=='en')['sha256']=digest_file(path)
                    args.dictionary_catalog.write_text(json.dumps(catalog))
                    for p in args.replacement_context_receipt:
                        r=json.loads(p.read_text());r['source_catalog_sha256']=digest_file(args.dictionary_catalog);p.write_text(json.dumps(r))
                with self.assertRaises(AssertionError):verify_recomputation(args,base,delta,out)

    def test_cumulative_pair_lineage_and_provenance(self):
        for mutation in [None,'drop-revision','wrong-provenance','missing-pair-corpus','wrong-pair-receipt']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory(dir='artifacts') as d:
                root=Path(d);args,base,delta=self.fixture(root);out=root/'proof';out.mkdir()
                old_rows=[json.loads(p.read_text()) for p in args.base_context_receipt]
                mixed=[]
                for row in old_rows:
                    current=dict(row,sha256='intermediate-'+row['sha256'],source_release_id='intermediate')
                    path=root/(current['sha256']+'.json');path.write_text(json.dumps(current))
                    mixed.append(path)
                args.base_context_receipt+=mixed
                first={'primary':'oldtatoeba','additional':['oldpgv']}
                second={'primary':'intermediate-oldtatoeba','additional':['intermediate-oldpgv']}
                base['pair_context_revisions']={pair:first if pair.startswith('en-') else second for pair in delta['requested_pairs']}
                base['pair_input_revisions']={pair:'w1' if pair.startswith('en-') else 'w2' for pair in delta['requested_pairs']}
                for revision,contexts in [('w1',first),('w2',second)]:
                    row=dict(complete=True,sha256=revision,source_release_id='historical',
                        requested_pairs=[p for p,v in base['pair_input_revisions'].items() if v==revision],
                        source_contexts_sha256=contexts['primary'],additional_contexts_sha256=contexts['additional'],
                        disjoint_source_proof=copy.deepcopy(delta['disjoint_source_proof']))
                    path=root/(revision+'.json');path.write_text(json.dumps(row));args.base_pair_receipt.append(path)
                if mutation=='drop-revision':args.base_context_receipt.pop()
                if mutation=='wrong-provenance':
                    path=mixed[0];row=json.loads(path.read_text());row['corpus_receipt_sha256']='wrong';path.write_text(json.dumps(row))
                if mutation=='missing-pair-corpus':
                    # Even if the global union still includes every corpus,
                    # one pair may not drop one of its own sources.
                    base['pair_context_revisions']['en-zh']={'primary':'oldtatoeba','additional':[]}
                    path=args.base_pair_receipt[0];row=json.loads(path.read_text());row['additional_contexts_sha256']=[];path.write_text(json.dumps(row))
                if mutation=='wrong-pair-receipt':
                    path=args.base_pair_receipt[1];row=json.loads(path.read_text());row['source_contexts_sha256']='oldtatoeba';path.write_text(json.dumps(row))
                if mutation:
                    with self.assertRaises(AssertionError):verify_recomputation(args,base,delta,out)
                else:
                    result,_=verify_recomputation(args,base,delta,out)
                    self.assertEqual(len(result['context_sources']),4)
                    self.assertEqual(result['pair_context_lineage']['en-zh'],['oldpgv','oldtatoeba'])

if __name__=='__main__':unittest.main()
