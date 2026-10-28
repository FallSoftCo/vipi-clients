import hashlib,json,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[2]
class NounContextEvidence(unittest.TestCase):
    def test_source_only_filter_keeps_unknown_and_competing_counterparts(self):
        with tempfile.TemporaryDirectory(prefix="vipi-noun-context-") as directory:
            root=Path(directory);path=root/"contexts.sqlite";filtered=root/"filter";filtered.mkdir()
            with closing(sqlite3.connect(path)) as db:
                db.executescript("""
                    CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT,text TEXT,owner TEXT);
                    CREATE TABLE alignments(a INTEGER,b INTEGER,a_start INTEGER,a_end INTEGER,b_start INTEGER,b_end INTEGER,a_lexeme INTEGER,b_lexeme INTEGER,kind INTEGER);
                    CREATE TABLE whole_past_forms(language TEXT,lexeme INTEGER,normalized TEXT,written TEXT,head TEXT);
                """)
                for i,(source,target) in enumerate([("home","casa"),("home","casa"),("home","hogar"),("home","unknown"),("book","libro")]):
                    a,b=i*2+1,i*2+2
                    db.executemany("INSERT INTO sentences VALUES (?,?,?,?)",[(a,"en","my "+source+" now "+str(i),"authored"),(b,"es","mi "+target+" ahora "+str(i),"authored")])
                    # Alternate stored pair orientation to check the pair OR
                    # clause cannot accidentally include nonlegacy records.
                    if i%2:a,b,source,target=b,a,target,source
                    for kind in (0,2):
                        db.execute("INSERT INTO alignments VALUES (?,?,?,?,?,?,?,?,?)",(a,b,3,3+len(source),3,3+len(target),0,0,kind))
                db.commit()
            release="a"*64;catalog="b"*64
            (root/"receipt.json").write_text(json.dumps(dict(complete=True,pilot=False,
                schema="vipi-broad-lexical-contexts-3",sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                languages=["en","es"],source_release_id=release,source_catalog_sha256=catalog)))
            (root/"ATTRIBUTION.txt").write_text("Authored filtering counterexamples.\n")
            selection=filtered/"source-words.sqlite"
            with closing(sqlite3.connect(selection)) as db:
                db.execute("CREATE TABLE source_words(language TEXT,word TEXT,PRIMARY KEY(language,word)) WITHOUT ROWID")
                db.executemany("INSERT INTO source_words VALUES (?,?)",[("en","home"),("es","casa")]);db.commit()
            (filtered/"receipt.json").write_text(json.dumps(dict(complete=True,schema="vipi-source-word-filter-1",
                policy="complete-explicit-noun-spellings-1",source_release_id=release,dictionary_catalog_sha256=catalog,
                sha256=hashlib.sha256(selection.read_bytes()).hexdigest())))
            output=root/"result"
            subprocess.run([sys.executable,str(ROOT/"language-packs/build_context_witnesses.py"),
                "--contexts",str(path),"--output",str(output),"--pair","en-es","--pair","es-en",
                "--source-word-filter",str(selection),"--observations-only"],check=True,stdout=subprocess.DEVNULL)
            receipt=json.loads((output/"receipt.json").read_text())
            self.assertEqual(receipt["counts"]["distinct_reference_spans"],5)
            self.assertTrue(receipt["all_matching_legacy_competing_targets_retained"])
            self.assertFalse((output/"witnesses.sqlite").exists())
            with closing(sqlite3.connect(output/"observations.sqlite")) as db:
                rows=db.execute("""SELECT t.value,count(*) FROM observations o JOIN pairs p ON p.id=o.pair
                    JOIN atoms w ON w.id=o.word JOIN atoms c ON c.id=o.cue JOIN atoms t ON t.id=o.target
                    WHERE p.source='en' AND w.value='home' AND c.value='L:my' GROUP BY t.value""").fetchall()
                self.assertEqual(dict(rows),{"casa":2,"hogar":1,"unknown":1})
                words=set(db.execute("SELECT DISTINCT p.source,w.value FROM observations o JOIN pairs p ON p.id=o.pair JOIN atoms w ON w.id=o.word"))
                self.assertEqual(words,{("en","home"),("es","casa")})
if __name__=="__main__":unittest.main()
