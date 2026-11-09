#!/usr/bin/env python3
"""Regression controls separating emitted vocabulary depth from context length."""
import importlib.util,json,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('head_review',HERE/'head_review.py');review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
class DepthControls(unittest.TestCase):
 def stratum(self,before,after):
  candidates=[]
  for side,depths in [('old',before),('new',after)]:
   for i,depth in enumerate(depths):
    candidates.append({'cost':1,'context_native_cost':depth,'focus_utf16':[i*2,i*2+1],'target':side+str(i),'reading':[],'fixed':side=='old'})
  row={'id':'synthetic','text':'test','candidates':candidates,'decisions':{k:{'fixed':{'selected_indices':list(range(len(before))),'mixed_output':'old'},'expanded':{'selected_indices':list(range(len(before),len(candidates))),'mixed_output':'new'}} for k in review.KNOWN}}
  selection=review.Selection(json.loads((HERE/'head-protocol-r01.json').read_text()),[]);selection.consider(row)
  return selection.freeze()['selected'][0]['stratum']
 def test_longer_context_but_fewer_emitted_words_is_loss(self):
  self.assertEqual(self.stratum([2,2],[8]),'depth_loss')
 def test_equal_emitted_words_with_shorter_context_is_not_loss(self):
  self.assertEqual(self.stratum([8],[2]),'other_change')
if __name__=='__main__':unittest.main()
