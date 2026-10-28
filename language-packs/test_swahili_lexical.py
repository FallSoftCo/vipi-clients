import json,sqlite3,unittest
from native_lemma_links import NativeLinks
from build_lexical_shards import native_senses
from swahili_lexical import derivation_definition,supplied_infinitive
import lexical_link_reviews

class SwahiliLexical(unittest.TestCase):
    def row(self,gloss,tags,refs):
        return (json.dumps([gloss]),json.dumps(tags),json.dumps(refs),"[]")

    def test_supplied_infinitive_backlink_recovers_root_without_guessing(self):
        db=sqlite3.connect(":memory:")
        db.executescript("""CREATE TABLE native_entries(source_line INTEGER PRIMARY KEY,
            language TEXT,headword TEXT,normalized TEXT,part_of_speech TEXT,tags TEXT,source_url TEXT);
            CREATE TABLE native_forms(source_line INTEGER,form TEXT,normalized TEXT,tags TEXT);""")
        db.executemany("INSERT INTO native_entries VALUES (?,'sw',?,?,'verb','[]','fixture')",
            [(1,"enda","enda"),(2,"kwenda","kwenda"),(3,"enda haja","enda haja"),(4,"enda","enda")])
        db.executemany("INSERT INTO native_forms VALUES (?,?,?,?)",
            [(1,"kwenda","kwenda",'["infinitive"]'),(3,"kwenda","kwenda",'["infinitive"]'),
             (4,"kwenda","kwenda",'["infinitive","archaic"]')])
        links=NativeLinks(db,"sw",{})
        try:
            self.assertEqual(links.candidates("kwenda","verb"),(1,2))
            self.assertEqual(links.candidates("kuenda","verb"),())
            self.assertEqual(links.candidates("Kwenda","verb"),(2,)) # Existing direct spelling lookup stays intact.
            db.execute("INSERT INTO native_entries VALUES (5,'sw','enda','enda','verb','[]','another meaning')")
            db.execute("INSERT INTO native_forms VALUES (5,'kwenda','kwenda','[\"infinitive\"]')")
            links.candidates.cache_clear()
            self.assertEqual(links.candidates("kwenda","verb"),(2,))

        finally:links.close();db.close()

    def test_derived_verb_retains_meaning_and_requires_explicit_definition(self):
        db=sqlite3.connect(":memory:")
        db.executescript("""CREATE TABLE native_entries(source_line INTEGER PRIMARY KEY,
            language TEXT,headword TEXT,normalized TEXT,part_of_speech TEXT,tags TEXT,source_url TEXT);
            CREATE TABLE native_senses(source_line INTEGER,glosses TEXT,tags TEXT,form_of TEXT,alt_of TEXT);
            CREATE TABLE native_forms(source_line INTEGER,form TEXT,normalized TEXT,tags TEXT);""")
        db.executemany("INSERT INTO native_entries VALUES (?,'sw',?,?,'verb','[]','fixture')",
            [(1,"kopa","kopa"),(2,"kopesha","kopesha"),(3,"badilisha","badilisha")])
        lend=self.row("Causative form of -kopa: to lend",["causative","form-of"],[dict(word="-kopa",extra="to lend")])
        unqualified=self.row("Causative form of kopa",["causative","form-of"],[dict(word="kopa",extra="")])
        db.execute("INSERT INTO native_senses VALUES (1,?,?,?,?)",self.row("to borrow",[],[]))
        db.execute("INSERT INTO native_senses VALUES (2,?,?,?,?)",lend)
        db.execute("INSERT INTO native_senses VALUES (3,?,?,?,?)",unqualified)
        links=NativeLinks(db,"sw",{})
        try:
            self.assertEqual(links.resolve(2),2)
            self.assertEqual(links.resolve(3),3) # No-extra derivations also cannot alias.
            self.assertTrue(links.derived_counterpart(2,"lend","to allow to be used temporarily"))
            self.assertFalse(links.derived_counterpart(2,"borrow","to receive temporarily"))
            self.assertFalse(links.derived_counterpart(3,"lend","to allow temporary use"))
            self.assertIsNone(links.derived_counterpart(1,"borrow","to receive temporarily"))
            # An ordinary definition beside a derivation remains available.
            db.execute("INSERT INTO native_senses VALUES (3,?,?,?,?)",self.row("to spell",[],[]))
            links.senses.cache_clear()
            self.assertIsNone(links.derived_counterpart(3,"spell","to write or say the letters that form a word"))
            # Its derived identity still must not collapse to the base.
            links.resolved.clear()
            self.assertEqual(links.resolve(3),3)

            self.assertEqual(native_senses([lend],"sw","verb"),(1,False))
            self.assertEqual(native_senses([unqualified],"sw","verb"),(0,True))
            self.assertEqual(native_senses([lend,unqualified],"sw","verb"),(1,True))
            several=self.row("Causative form of -lingana: to compare, equate, correlate",
                ["causative","form-of"],[dict(word="-lingana",extra="to compare, equate, correlate")])
            self.assertEqual(native_senses([several],"sw","verb"),(1,True))
            self.assertEqual(native_senses([lend],"es","verb"),(0,True))
        finally:links.close();db.close()

    def test_reviewed_causative_sense_does_not_change_state_by_itself(self):
        sense="b28657b739604b237b65cd34b5d3c903963202bdb8c1b890feb1e086fc7cdf29"
        self.assertTrue(lexical_link_reviews.rejected("sw",2168820,sense,"to become stable"))
        self.assertFalse(lexical_link_reviews.rejected("sw",2168820,"different-sense","to make stable"))
        self.assertFalse(lexical_link_reviews.rejected("sw",7906598,sense,"to become stable"))
        with self.assertRaises(AssertionError):
            lexical_link_reviews.rejected("sw",2168820,sense,"changed upstream meaning")

    def test_qualified_or_conflicting_derivations_and_invented_forms_are_rejected(self):
        refs=[dict(word="-kopa",extra="to lend")]
        for tags in [["form-of","causative","archaic"],["form-of","causative","figuratively"],
                     ["form-of","causative","passive"],["form-of","infinitive"]]:
            self.assertIsNone(derivation_definition("sw","verb",["Causative form of -kopa: to lend"],tags,refs,[]))
        self.assertIsNone(derivation_definition("sw","verb",["Causative form of -kopa: to borrow"],
            ["form-of","causative"],refs,[]))
        for language,head,pos,form,tags in [
            ("en","enda","verb","kwenda",["infinitive"]),
            ("sw","enda haja","verb","kwenda",["infinitive"]),
            ("sw","enda","verb","ninakwenda",["infinitive"]),
            ("sw","enda","verb","Kwenda",["infinitive"]),
            ("sw","enda","noun","kwenda",["infinitive"])]:
            self.assertFalse(supplied_infinitive(language,head,pos,form,tags))

if __name__=="__main__":unittest.main()
