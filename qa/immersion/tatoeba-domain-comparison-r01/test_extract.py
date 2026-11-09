"""Synthetic schema checks only: never opens a retained corpus."""
import sqlite3,unittest
from extract import SQL,BAD,reviewed_blocked_ids
class ExtractionContract(unittest.TestCase):
 def test_metadata_both_orientations_and_reserved_exclusion(self):
  db=sqlite3.connect(':memory:')
  db.executescript('CREATE TABLE sentences(id,language,owner,component,partition); CREATE TABLE links(a,b);')
  db.executemany('INSERT INTO sentences VALUES(?,?,?,?,?)',[(1,'en','a',1,'development'),(2,'es','b',1,'development'),(3,'es','c',3,'development'),(4,'en','d',3,'development'),(5,'en','e',5,'reserved'),(6,'es','f',5,'development')])
  db.executemany('INSERT INTO links VALUES(?,?)',[(1,2),(3,4),(5,6)])
  self.assertEqual([r[:2] for r in db.execute(SQL)],[(1,2),(3,4)])
  # No text/normalized column exists in fixture: selection cannot read either.
 def test_flag_policy_preserves_ambiguous_tags(self):
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE tag_metadata(id,name)')
  db.executemany('INSERT INTO tag_metadata VALUES(?,?)',[(1,'@needs_native_check'),(2,'unnatural'),(3,'less than natural'),(4,'colloquial'),(5,'unchecked'),(6,'incorrect spelling')])
  self.assertEqual([r[0] for r in db.execute('SELECT id FROM tag_metadata WHERE '+BAD)],[1,2,3,6])
 def test_metadata_review_does_not_confuse_topic_or_audio_with_text_errors(self):
  names={1:'politically incorrect',2:'incorrect grammar',3:'@delete audio',4:'@delete'}
  review={'retained_non_text_flags':[{'id':1,'name':names[1]},{'id':3,'name':names[3]}]}
  self.assertEqual(reviewed_blocked_ids(names,{1,2,3,4},review),{2,4})
  with self.assertRaises(AssertionError):reviewed_blocked_ids({**names,1:'incorrect translation'},{1,2,3,4},review)
if __name__=='__main__':unittest.main()
