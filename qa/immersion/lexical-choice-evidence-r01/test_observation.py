import copy,unittest
from diagnose import verify_observation
class JoinControl(unittest.TestCase):
 def test_exact_pair_and_geometry(self):
  token=lambda word:{'text':word,'codepoints':[0,len(word)],'utf16':[0,len(word)]}
  pair={'index':0,'pair_id':'pair-A','source':{'text':'cat','component':7,'tokens':[token('cat')]},'target':{'text':'gato','component':7,'tokens':[token('gato')]}}
  obs={'pair_index':0,'pair_id':'pair-A','component':7,'source_tokens':[0,1],'target_tokens':[0,1],'source_codepoints':[0,3],'target_codepoints':[0,4],'source_utf16':[0,3],'target_utf16':[0,4]};variant={'source_key':'cat','target_key':'gato'}
  verify_observation(pair,obs,variant,str.casefold)
  for key,value in [('pair_id','wrong'),('component',8),('source_tokens',[0,2]),('target_tokens',[-1,1])]:
   bad=copy.deepcopy(obs);bad[key]=value
   with self.assertRaises(AssertionError):verify_observation(pair,bad,variant,str.casefold)
  with self.assertRaises(AssertionError):verify_observation(pair,obs,dict(variant,target_key='perro'),str.casefold)
if __name__=='__main__':unittest.main()
