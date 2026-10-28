import json,sqlite3,unittest
from native_lemma_links import NativeLinks

class NativeGlossArticles(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE native_entries(source_line INTEGER,headword TEXT,normalized TEXT,part_of_speech TEXT,tags TEXT,source_url TEXT,language TEXT);
            CREATE TABLE native_senses(source_line INTEGER,glosses TEXT,tags TEXT,form_of TEXT,alt_of TEXT);
        """)
        self.links=NativeLinks(self.db,"de",{})
    def tearDown(self):self.db.close()
    def add(self,i,gloss,pos="noun",tags=(),forms=()):
        self.db.execute("INSERT INTO native_entries VALUES (?,?,?,?,?,?,?)",(i,"word","word",pos,"[]","test","de"))
        self.db.execute("INSERT INTO native_senses VALUES (?,?,?,?,?)",(i,json.dumps([gloss]),json.dumps(tags),json.dumps(forms),"[]"))
    def test_articles_preserve_existing_noun_meaning_only(self):
        self.add(1,"an island, an isle",tags=["feminine"])
        self.assertEqual(self.links.simple_glosses(1),{"an island","an isle","island","isle"})
        self.add(2,"a dog")
        self.assertEqual(self.links.simple_glosses(2),{"a dog","dog"})
        self.add(3,"a bank")
        self.assertNotIn("shore",self.links.simple_glosses(3))
    def test_does_not_extract_words_from_descriptions_or_aliases(self):
        self.add(4,"an island surrounded by water")
        self.assertEqual(self.links.simple_glosses(4),set())
        self.add(5,"an old island")
        self.assertEqual(self.links.simple_glosses(5),set())
        self.add(6,"an island",forms=[{"word":"Island"}])
        self.assertEqual(self.links.simple_glosses(6),set())
        self.add(7,"an island",tags=["obsolete"])
        self.assertEqual(self.links.simple_glosses(7),set())
        self.add(8,"an island",pos="verb")
        self.assertEqual(self.links.simple_glosses(8),{"an island"})
if __name__=="__main__":unittest.main()
