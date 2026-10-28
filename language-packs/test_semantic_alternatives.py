import sqlite3,unittest
from contextlib import closing
from build_semantic_alternatives import qualify,NounRelations,AdjectiveRelations
class AlternativeEvidence(unittest.TestCase):
    def test_synonyms_share_a_relation_without_duplicate_votes(self):
        rows=[]
        for sid in range(1,7):
            head="beber" if sid<=3 else "tomar"
            rows.append((sid,sid+10,head,{"consume-liquid"}))
        rows.append(rows[0])
        got={r["head"]:r for r in qualify(rows)}
        self.assertEqual(set(got),{"beber","tomar"})
        self.assertTrue(all((r["support"],r["total"],r["counterpart_support"])==(6,6,3) for r in got.values()))
    def test_unrelated_meanings_remain_competing(self):
        rows=[(i,i+10,"orilla",{"river-edge"}) for i in range(3)]
        rows.append((4,14,"banco",{"financial-institution"}))
        self.assertEqual(qualify(rows),[])
    def test_unknown_is_not_dropped(self):
        rows=[(i,i+10,"beber",{"consume-liquid"}) for i in range(3)]
        rows.append((4,14,None,set()))
        self.assertEqual(qualify(rows),[])
    def test_conflicting_targets_in_one_sentence_do_not_cast_positive_votes(self):
        rows=[(i,i+10,"orilla",{"river-edge"}) for i in range(3)]
        rows.append((0,20,"banco",{"financial-institution"}))
        self.assertEqual(qualify(rows),[])
    def test_one_sentence_with_many_paraphrases_is_not_three_sources(self):
        self.assertEqual(qualify([(1,10,"beber",{"drink"}),(1,11,"tomar",{"drink"}),(1,12,"beber",{"drink"})]),[])
    def test_rare_counterpart_cannot_borrow_all_synonym_support(self):
        rows=[(i,i+10,"beber",{"drink"}) for i in range(5)]+[(6,16,"tomar",{"drink"})]
        self.assertEqual([r["head"] for r in qualify(rows)],["beber"])
class NounRelationEvidence(unittest.TestCase):
    def test_whole_nouns_keep_unknowns_partial_stems_and_competing_heads_out(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.executescript("""
                CREATE TABLE lexemes(id INTEGER PRIMARY KEY,normalized TEXT,pos TEXT,target_safe INTEGER);
                CREATE TABLE terms(lexeme INTEGER,sense TEXT,eligible INTEGER);
                CREATE TABLE senses(id TEXT PRIMARY KEY,explicit INTEGER);
                CREATE TABLE surfaces(normalized TEXT,lexeme INTEGER,surface TEXT,start INTEGER,end INTEGER,mode INTEGER);
                CREATE INDEX surface_lookup ON surfaces(normalized);
            """)
            db.executemany("INSERT INTO lexemes VALUES (?,?,?,?)",[(1,"house","noun",1),(2,"home","noun",1),
                (3,"house","verb",1),(4,"other","noun",1)])
            db.executemany("INSERT INTO senses VALUES (?,?)",[("dwelling",1),("inferred",0),("unrelated",1)])
            db.executemany("INSERT INTO terms VALUES (?,?,?)",[(1,"dwelling",1),(1,"inferred",1),(1,"unrelated",0),
                (2,"dwelling",1),(3,"unrelated",1),(4,"unrelated",1)])
            db.executemany("INSERT INTO surfaces VALUES (?,?,?,?,?,?)",[("house",1,"house",0,5,1),
                ("homes",2,"homes",0,5,2),("houses",1,"houses",0,5,3),("houses",3,"houses",0,6,2),
                ("ambiguous",1,"ambiguous",0,9,1),("ambiguous",4,"ambiguous",0,9,1),
                ("😀home",2,"😀home",0,6,2)])
            index=NounRelations(db)
            self.assertEqual(index.source_relations("house"),{"dwelling"})
            self.assertEqual(index.source_relations("homes"),{"dwelling"})
            self.assertEqual(index.source_relations("😀home"),{"dwelling"})
            self.assertFalse(index.heads("houses"))
            self.assertFalse(index.heads("unknown"))
            self.assertFalse(index.source_relations("ambiguous"))
            self.assertFalse(index.heads("@present:house"))
class AdjectiveRelationEvidence(unittest.TestCase):
    def test_whole_adjectives_do_not_borrow_nouns_stems_or_ambiguous_heads(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.executescript("""
                CREATE TABLE lexemes(id INTEGER PRIMARY KEY,normalized TEXT,pos TEXT,target_safe INTEGER);
                CREATE TABLE terms(lexeme INTEGER,sense TEXT,eligible INTEGER);
                CREATE TABLE senses(id TEXT PRIMARY KEY,explicit INTEGER);
                CREATE TABLE surfaces(normalized TEXT,lexeme INTEGER,surface TEXT,start INTEGER,end INTEGER,mode INTEGER);
            """)
            db.executemany("INSERT INTO lexemes VALUES (?,?,?,?)",[(1,"caro","adj",1),(2,"cara","noun",1),(3,"caro","noun",1),(4,"otro","adj",1)])
            db.executemany("INSERT INTO senses VALUES (?,?)",[("costly",1),("face",1),("inferred",0)])
            db.executemany("INSERT INTO terms VALUES (?,?,?)",[(1,"costly",1),(1,"inferred",1),(2,"face",1),(3,"face",1),(4,"face",1)])
            db.executemany("INSERT INTO surfaces VALUES (?,?,?,?,?,?)",[("cara",1,"cara",0,4,2),("cara",2,"cara",0,4,1),
                ("caro",1,"caro",0,4,1),("caros",1,"caros",0,4,3),("caras",1,"caras",0,5,2),
                ("ambiguous",1,"ambiguous",0,9,1),("ambiguous",4,"ambiguous",0,9,1)])
            index=AdjectiveRelations(db)
            self.assertEqual(index.source_relations("cara"),{"costly"})
            self.assertEqual(index.source_relations("caras"),{"costly"})
            self.assertFalse(index.heads("caros"))
            self.assertFalse(index.heads("unknown"))
            self.assertFalse(index.source_relations("ambiguous"))
            self.assertFalse(NounRelations(db).source_relations("caras"))
if __name__=="__main__":unittest.main()
