import hashlib,json,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[2]
class PresentContextEvidence(unittest.TestCase):
    def test_infinitive_opposite_endpoint_stays_in_denominator(self):
        with tempfile.TemporaryDirectory(prefix="vipi-present-context-") as directory:
            root=Path(directory);path=root/"contexts.sqlite"
            with closing(sqlite3.connect(path)) as db:
                db.executescript("""
                    CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT,text TEXT,owner TEXT);
                    CREATE TABLE alignments(a INTEGER,b INTEGER,a_start INTEGER,a_end INTEGER,b_start INTEGER,b_end INTEGER,a_lexeme INTEGER,b_lexeme INTEGER,kind INTEGER);
                    CREATE TABLE lexicon(language TEXT,normalized TEXT,analyses TEXT);
                    CREATE TABLE whole_past_forms(language TEXT,lexeme INTEGER,normalized TEXT,written TEXT,head TEXT);
                    CREATE TABLE whole_present_forms(language TEXT,lexeme INTEGER,normalized TEXT,written TEXT,head TEXT);
                """)
                for lang,lexeme,written,head in [("en",1,"work","work"),("es",2,"trabajo","trabajar")]:
                    db.execute("INSERT INTO whole_present_forms VALUES (?,?,?,?,?)",(lang,lexeme,written,written,head))
                    analyses=[[lexeme,1,[],[[5,written,0,len(written),["present-person-1s"]]]]]
                    db.execute("INSERT INTO lexicon VALUES (?,?,?)",(lang,written,json.dumps(analyses)))
                for i,tail in enumerate(["one","two","three","four"]):
                    a,b=i*2+1,i*2+2
                    original=("I work" if i<3 else "I hope to work")+" at home "+tail
                    translation="Trabajo en casa "+tail
                    db.executemany("INSERT INTO sentences VALUES (?,?,?,?)",[(a,"en",original,"synthetic"),(b,"es",translation,"synthetic")])
                    start=original.index("work")
                    db.execute("INSERT INTO alignments VALUES (?,?,?,?,?,?,?,?,?)",(a,b,start,start+4,0,7,1,2,2))
                    db.execute("INSERT INTO alignments VALUES (?,?,?,?,?,?,?,?,?)",(a,b,start,start+4,0,7,1,2,0))
                db.commit()
            (root/"receipt.json").write_text(json.dumps(dict(complete=True,pilot=False,
                schema="vipi-broad-lexical-contexts-3",sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                languages=["en","es"],source_release_id="a"*64)))
            (root/"ATTRIBUTION.txt").write_text("Authored positive and deliberate conflicting endpoint fixture.\n")
            output=root/"result"
            subprocess.run([sys.executable,str(ROOT/"language-packs/build_context_witnesses.py"),
                "--contexts",str(path),"--output",str(output),"--pair","en-es","--pair","es-en"],
                check=True,stdout=subprocess.DEVNULL)
            with closing(sqlite3.connect(output/"witnesses.sqlite")) as db:
                self.assertEqual(db.execute("SELECT support,total FROM witnesses WHERE source='en' AND word='work' AND counterpart='trabajo' AND cue='R:home'").fetchone(),(4,4))
                self.assertEqual(db.execute("SELECT support,total FROM witnesses WHERE source='en' AND word='@present:work' AND counterpart='@present:trabajar' AND cue='R:home'").fetchone(),(3,3))
                self.assertIsNone(db.execute("SELECT 1 FROM witnesses WHERE source='es' AND word='@present:trabajar' AND cue='R:casa'").fetchone())
            with closing(sqlite3.connect(output/"observations.sqlite")) as db:
                rows=db.execute("""SELECT t.value,count(*) FROM observations o JOIN pairs p ON p.id=o.pair
                    JOIN atoms w ON w.id=o.word JOIN atoms c ON c.id=o.cue JOIN atoms t ON t.id=o.target
                    WHERE p.source='es' AND w.value='@present:trabajar' AND c.value='R:casa' GROUP BY t.value""").fetchall()
                self.assertEqual(dict(rows),{"@present:work":3,"work":1})
if __name__=="__main__":unittest.main()
