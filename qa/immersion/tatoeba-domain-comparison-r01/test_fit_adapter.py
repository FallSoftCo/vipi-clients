import hashlib,math,unittest
from pathlib import Path
from fit_phrases import pure_functions,command_plan
class Adapter(unittest.TestCase):
 def test_hash_bound_geometry_score_and_normalization(self):
  p=Path(__file__).resolve().parent.parent/'corpus-phrase-extraction-r01'
  hashes={n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ['extract_phrases.py','prepare_inputs.py']}
  f,b=pure_functions(p/'extract_phrases.py',p/'prepare_inputs.py',hashes)
  self.assertEqual(set(b),{'crosses_stop','consistent_targets','parse_links','lexical_score','norm'})
  self.assertEqual(set(f['consistent_targets'](0,1,['a','b','c'],{(0,1)})),{(0,2,1,2),(0,3,1,2),(1,2,1,2),(1,3,1,2)})
  self.assertEqual(f['consistent_targets'](0,1,['a'],{(0,0),(1,0)}),[])
  self.assertEqual(f['norm']('  CAFÉ  '),'café')
  score,missing=f['lexical_score'](['a'],['b'],{(0,0)},{},{})
  self.assertEqual(missing,2);self.assertAlmostEqual(score,math.log(1e-12))
  self.assertNotIn('main',f);self.assertNotIn('OUT',f)
 def test_single_frozen_three_commands(self):
  commands=command_plan();self.assertEqual(len(commands),3)
  self.assertEqual(commands[1]['argv'][-1],'-r');self.assertEqual(commands[2]['argv'][-1],'grow-diag-final-and')
  for c in commands[:2]:self.assertEqual(c['argv'][c['argv'].index('-I')+1],'5')
if __name__=='__main__':unittest.main()
