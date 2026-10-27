import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from rebind_context_witnesses import prove


class ContextRebinding(unittest.TestCase):
    def fixture(self,path):
        with sqlite3.connect(path) as db:
            for table in ["terms","senses","lexemes","surfaces"]:
                db.execute("CREATE TABLE "+table+"(id INTEGER PRIMARY KEY,value TEXT)")
                db.execute("INSERT INTO "+table+" VALUES (1,'retained')")
            db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")
            db.executemany("INSERT INTO metadata VALUES (?,?)",[(k,json.dumps("same")) for k in
                ["source_inventory_sha256","source_sha256","redirects_sha256","native_gloss_links_sha256","linker_sha256","language"]])
            db.execute("INSERT INTO metadata VALUES ('policy',?)",(json.dumps("native-linked-noun-carriers-5"),))

    def test_new_forms_and_negative_analyses_cannot_change_dictionary_meanings(self):
        with tempfile.TemporaryDirectory(dir="artifacts") as temporary:
            old=Path(temporary)/"old.sqlite";new=Path(temporary)/"new.sqlite"
            self.fixture(old);self.fixture(new)
            with sqlite3.connect(new) as db:
                db.execute("INSERT INTO surfaces VALUES (2,'new carrier')")
                db.execute("INSERT INTO lexemes VALUES (2,'competing native analysis')")
            self.assertEqual(prove(old,new)["surfaces_added"],1)
            for table,query in [
                ("terms","INSERT INTO terms VALUES (2,'new translation')"),
                ("terms","UPDATE terms SET value='changed meaning' WHERE id=1"),
                ("surfaces","DELETE FROM surfaces WHERE id=1"),
                ("metadata","UPDATE metadata SET value='changed' WHERE key='source_inventory_sha256'")]:
                with sqlite3.connect(new) as db:
                    db.execute("BEGIN");db.execute(query);db.commit()
                with self.assertRaises(AssertionError):prove(old,new)
                new.unlink();self.fixture(new)


if __name__=="__main__":unittest.main()
