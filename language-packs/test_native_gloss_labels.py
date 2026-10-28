import json,sqlite3,unittest
from native_lemma_links import NativeLinks

class NativeGlossLabels(unittest.TestCase):
    def test_only_the_exact_unqualified_sense_label_is_corroborated(self):
        db=sqlite3.connect(":memory:")
        db.executescript("""
            CREATE TABLE native_senses(source_line INTEGER,glosses TEXT,tags TEXT,form_of TEXT,alt_of TEXT);
        """)
        def add(i,gloss,tags=(),forms=()):
            db.execute("INSERT INTO native_senses VALUES (?,?,?,?,?)",(i,json.dumps([gloss]),json.dumps(tags),json.dumps(forms),"[]"))
        add(1,"medical doctor")
        add(2,"medical doctor",tags=["archaic"])
        add(3,"medical doctor",forms=[{"word":"different"}])
        add(4,"medical doctor");add(4,"teacher")
        add(5,"medical doctor",tags=["figuratively"])
        links=NativeLinks(db,"ja",{})
        try:
            self.assertTrue(links.matching_sense_gloss(1,"medical doctor"))
            self.assertTrue(links.matching_sense_gloss(1,"Medical doctor."))
            for label in ["doctor","academic title","teacher","medical"]:
                self.assertFalse(links.matching_sense_gloss(1,label))
            for identifier in [2,3,4,5]:
                self.assertFalse(links.matching_sense_gloss(identifier,"medical doctor"))
        finally:links.close();db.close()

if __name__=="__main__":unittest.main()
