import copy,unittest
from mechanism import rescued_link,occurrence_reasons,competition
class Controls(unittest.TestCase):
 def setUp(self):
  self.guard={'reason':'name','blocked':1,'target_blocked':0}
  term={'term_id':'s','sense_id':'meaning','eligible':True,'explicit':True,'reasons':[]}
  self.s={'pos':'noun','complete':True,'mode':1,'number':'singular','reasons':['dictionary_guard'],'terms':[term]}
  self.t=copy.deepcopy(self.s);self.t['reasons']=[];self.t['terms'][0]['term_id']='t'
  self.m={'source_term_id':'s','target_term_id':'t','sense_id':'meaning','source_pos':'noun','target_pos':'noun','source_number':'singular','target_number':'singular','reasons':['dictionary_guard'],'structural_eligible':False}
 def test_narrow_link(self):
  self.assertTrue(rescued_link(self.m,self.s,self.t,self.guard))
  for reason in ['dictionary_guard','historical_capitalization_guard','incomplete_dictionary_form','unsupported_form_mode','unsupported_pos','dictionary_target_unsafe']:
   t=copy.deepcopy(self.t);t['reasons']=[reason];self.assertFalse(rescued_link(self.m,self.s,t,self.guard))
  for field,value in [('pos','verb'),('complete',False),('mode',3),('number','plural')]:
   s=copy.deepcopy(self.s);s[field]=value;self.assertFalse(rescued_link(self.m,s,self.t,self.guard))
  for field,value in [('explicit',False),('eligible',False)]:
   s=copy.deepcopy(self.s);s['terms'][0][field]=value;self.assertFalse(rescued_link(self.m,s,self.t,self.guard))
  for reason in ['grammar','name,grammar','native-word-boundary']:
   self.assertFalse(rescued_link(self.m,self.s,self.t,dict(self.guard,reason=reason)))
  s=copy.deepcopy(self.s);s['reasons'].append('historical_capitalization_guard');self.assertFalse(rescued_link(self.m,s,self.t,self.guard))
 def test_occurrence(self):
  c={'role':{'raw':['NOUN',.9]},'category':'content','cost':1,'source':'boys','filter_reasons':[]}
  self.assertEqual(occurrence_reasons(c),[])
  for raw in [None,['PROPN',.99],['ADJ',.99]]:
   self.assertTrue(occurrence_reasons(dict(c,role={'raw':raw})))
  self.assertTrue(occurrence_reasons(dict(c,source='Boys')))
  self.assertTrue(occurrence_reasons(dict(c,filter_reasons=['not_single_token_head'])))
 def test_competing_geometry(self):
  self.assertEqual(competition([('old',[1,2],[3,4]),('rescued',[1,2],[4,5])]),{'old','rescued'})
  self.assertEqual(competition([('old',[1,2],[3,4]),('synonym',[1,2],[3,4])]),set())
if __name__=='__main__':unittest.main()
