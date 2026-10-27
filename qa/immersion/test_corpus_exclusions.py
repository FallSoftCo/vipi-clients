import argparse
import bz2
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from build_corpus_exclusions import build,fingerprint
from conversation_corpus import sha_file


class CorpusExclusions(unittest.TestCase):
    def test_both_partitions_and_swahili_are_bound_without_persisting_text(self):
        with tempfile.TemporaryDirectory(dir="artifacts") as temporary:
            root=Path(temporary);primary=root/"primary";primary.mkdir();sw=root/"sw";sw.mkdir()
            path=primary/"corpus.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE sentences(language TEXT,normalized TEXT,partition TEXT)")
                db.executemany("INSERT INTO sentences VALUES (?,?,?)",[
                    ("en","private held-out fixture.","reserved"),("en","development fixture.","development")])
            (primary/"receipt.json").write_text(json.dumps(dict(sha256=sha_file(path))))
            source=sw/"swh_sentences_detailed.tsv.bz2"
            with bz2.open(source,"wt") as f:f.write("1\tswh\tSwahili fixture.\towner\n")
            (sw/"receipt.json").write_text(json.dumps(dict(sha256=sha_file(source))))
            out=root/"output";build(argparse.Namespace(corpus=path,swahili=sw,output=out))
            with sqlite3.connect(out/"hashes.sqlite") as db:
                for language,text in [("en","Private  held-out fixture."),("en","development fixture."),("sw","Swahili fixture.")]:
                    self.assertEqual(db.execute("SELECT count(*) FROM hashes WHERE digest=?",(fingerprint(language,text),)).fetchone()[0],1)
                self.assertEqual(db.execute("SELECT count(*) FROM hashes WHERE digest=?",(fingerprint("es","private held-out fixture."),)).fetchone()[0],0)
            self.assertNotIn(b"private held-out fixture",(out/"hashes.sqlite").read_bytes())
            self.assertEqual(fingerprint("fr","Cafe\u0301."),fingerprint("fr","CAFÉ."))
            self.assertNotEqual(fingerprint("en","fixture"),fingerprint("en","fixture."))


if __name__=="__main__":unittest.main()
