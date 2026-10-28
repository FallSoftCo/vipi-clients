import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa/immersion'))
from add_arabic_plural_readings import candidates,head_readings,reading_key,RULE,POLICY
from build_lexical_contexts import load_lexicon,unique_hits

class ArabicPluralReadings(unittest.TestCase):
    def test_supplied_plural_and_definite_focus(self):
        rows=[(1,'كُتُب','kutub',json.dumps(['plural'])),
              (2,'الْكُتُب','al-kutub',json.dumps(['definite','plural'])),
              (3,'كُتُبٌ','kutubun',json.dumps(['plural','nominative'])),
              (4,'كِتَابَان','kitābān',json.dumps(['dual']))]
        forms={r['written']:r for r in candidates(rows)}
        self.assertEqual(set(forms),{'كتب','الكتب'})
        self.assertEqual(forms['الكتب']['focus_start'],2)
        self.assertEqual(forms['الكتب']['reading'],'kutub')
    def test_singular_reading_keeps_homographs_separate(self):
        rows=[(1,'كِتَاب','kitāb','["singular","indefinite","informal"]'),
              (2,'كِتَابٌ','kitābun','["singular","nominative"]'),
              (3,'كُتُب','kutub','["plural"]')]
        self.assertEqual(head_readings(rows,'كتاب'),{'kitāb'})
        self.assertNotIn(reading_key('kuttāb'),head_readings(rows,'كتاب'))
        self.assertEqual(reading_key("ḥiḏā'"),reading_key('ḥiḏāʔ'))
    def test_ambiguous_reading_is_not_guessed(self):
        self.assertEqual(list(candidates([(1,'كتب','kutub','["plural"]'),(2,'كتب','katab','["plural"]')])),[])
    def test_context_reading_never_falls_back_to_singular(self):
        for readings in [('kutub',),(),('kutub','katab')]:
            with self.subTest(readings=readings),tempfile.TemporaryDirectory(dir='artifacts') as folder:
                path=Path(folder)/'ar.sqlite'
                db=sqlite3.connect(path)
                db.executescript("""
                CREATE TABLE metadata(key TEXT,value TEXT);
                CREATE TABLE lexemes(id INTEGER,source_safe INTEGER,target_safe INTEGER);
                CREATE TABLE senses(id TEXT,explicit INTEGER);
                CREATE TABLE terms(lexeme INTEGER,sense TEXT,reading TEXT,eligible INTEGER);
                CREATE TABLE surfaces(normalized TEXT,lexeme INTEGER,mode INTEGER,surface TEXT,start INTEGER,end INTEGER,features TEXT);
                CREATE TABLE surface_readings(normalized TEXT,lexeme INTEGER,sense TEXT,reading TEXT);
                INSERT INTO lexemes VALUES(1,1,1);
                INSERT INTO senses VALUES('book',1); INSERT INTO senses VALUES('school',1);
                INSERT INTO terms VALUES(1,'book','kitāb',1); INSERT INTO terms VALUES(1,'school','kuttāb',1);
                """)
                db.executemany('INSERT INTO metadata VALUES (?,?)',[(k,json.dumps(v)) for k,v in
                    dict(policy=POLICY,surface_reading_schema='vipi-surface-reading-2',surface_reading_rule=RULE).items()])
                db.execute('INSERT INTO surfaces VALUES (?,?,?,?,?,?,?)',('الكتب',1,3,'الكتب',2,5,json.dumps([RULE,'plural'])))
                db.executemany('INSERT INTO surface_readings VALUES (?,?,?,?)',[('الكتب',1,'book',r) for r in readings])
                db.commit();db.close()
                output=sqlite3.connect(Path(folder)/'output.sqlite')
                output.execute('CREATE TABLE lexicon(id INTEGER,language TEXT,normalized TEXT,analyses TEXT)')
                _,forms=load_lexicon(path,'ar',{'book':1,'school':2},output)
                analyses={form[2]:form[1] for form in forms}
                form_id=forms[0][2]
                hits=unique_hits(json.dumps([[form_id,0,5,'الكتب']]),analyses.__getitem__)
                self.assertNotIn(2,hits)  # Plural of kitāb must not inherit kuttāb's school sense.
                if len(readings)==1:
                    self.assertEqual(hits[1][0:2],(2,5))
                    self.assertEqual(hits[1][4],'kutub')
                else:self.assertEqual(hits,{})
                # Exact supplied geometry must not consume marked text with
                # different offsets or infer its pronunciation.
                self.assertEqual(unique_hits(json.dumps([[form_id,0,7,'الْكُتب']]),analyses.__getitem__),{})
                output.close()
if __name__=='__main__':unittest.main()
