import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from build_corpus_exclusions import fingerprint
from conversation_corpus import sha_file
from import_parallel_global_voices import build,XML_LANG


class ParallelGlobalVoices(unittest.TestCase):
    def test_exclusions_propagate_duplicates_do_not_inflate_and_links_never_pivot(self):
        with tempfile.TemporaryDirectory(dir="artifacts") as temporary:
            root=Path(temporary);source=root/"source";source.mkdir();exclude=root/"exclude";exclude.mkdir()
            hashes=exclude/"hashes.sqlite"
            with sqlite3.connect(hashes) as db:
                db.execute("CREATE TABLE hashes(digest BLOB PRIMARY KEY)")
                db.execute("INSERT INTO hashes VALUES (?)",(fingerprint("en","Reserved sentence."),))
            (exclude/"receipt.json").write_text(json.dumps(dict(schema="vipi-existing-corpus-exclusions-1",complete=True,sha256=sha_file(hashes))))
            archives=[]
            for pair,rows in [
                ("eng-swa",[("Reserved sentence.","Sentensi iliyohifadhiwa.",2),
                            ("New sentence.","Sentensi mpya.",3),("NEW  sentence.","Sentensi mpya.",3),
                            ("Invalid score.","Alama.",float("nan")),("Empty target.","",2)]),
                ("fra-swa",[("Phrase réservée.","SENTENSI iliyohifadhiwa.",2),("Nouvelle phrase.","Sentensi mpya.",3)])]:
                tmx=ET.Element("tmx");body=ET.SubElement(tmx,"body")
                for index,(left,right,score) in enumerate(rows,1):
                    unit=ET.SubElement(body,"tu",tuid=str(index));ET.SubElement(unit,"prop",type="score").text=str(score)
                    for language,text in zip(pair.split("-"),[left,right]):
                        variant=ET.SubElement(unit,"tuv",{XML_LANG:language});ET.SubElement(variant,"seg").text=text
                path=source/(pair+".zip")
                with zipfile.ZipFile(path,"w") as archive:archive.writestr("pgv/"+pair+".tmx",ET.tostring(tmx))
                archives.append(dict(pair=pair,url="https://example.test/"+pair+".zip",bytes=path.stat().st_size,sha256=sha_file(path)))
            (source/"receipt.json").write_text(json.dumps(dict(schema="vipi-pgv-acquisition-1",complete=True,archives=archives,citation="Synthetic corpus fixture.")))
            out=root/"output";build(argparse.Namespace(source=source,exclusions=hashes,output=out,language="sw"))
            receipt=json.loads((out/"receipt.json").read_text())
            self.assertEqual(receipt["sentences"],6)
            self.assertEqual(receipt["direct_links"],4)
            self.assertEqual(receipt["partitions"],{"excluded-existing-source":3,"development":3})
            self.assertEqual(receipt["counts"]["empty_nonpositive_or_oversized"],2)
            with sqlite3.connect(out/"corpus.sqlite") as db:
                self.assertEqual(db.execute("SELECT count(*) FROM sentences WHERE id>=0").fetchone()[0],0)
                self.assertEqual(db.execute("SELECT count(*) FROM links l JOIN sentences a ON a.id=l.a JOIN sentences b ON b.id=l.b WHERE a.language<>'sw' AND b.language<>'sw'").fetchone()[0],0)
                self.assertEqual(db.execute("SELECT count(*) FROM link_evidence").fetchone()[0],5)
                self.assertEqual(db.execute("SELECT count(*) FROM attribution").fetchone()[0],10)
            self.assertEqual(receipt["sha256"],sha_file(out/"corpus.sqlite"))


if __name__=="__main__":unittest.main()
