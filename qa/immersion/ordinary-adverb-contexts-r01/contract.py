"""Conservative ADV base-form qualification; no source or target guard overrides."""
import re,unicodedata
def norm(s):return ' '.join(unicodedata.normalize('NFC',s).casefold().split())
def base_reasons(form,role):
 reasons=list(form['reasons'])
 if form['pos']!='adv':reasons.append('dictionary_not_ADV')
 if not form['complete'] or form['mode'] not in (1,2):reasons.append('incomplete_or_unsupported_form')
 if form['features']:reasons.append('nonempty_form_features_not_qualified')
 if norm(form['surface'])!=norm(form['headword']):reasons.append('not_base_headword_surface')
 if not role or role['chosen_roles']!=['ADV'] or role['unknown'] or role['joined_morphemes']:reasons.append('not_exact_unambiguous_actual_ADV')
 else:
  readings=role['readings']
  if len(readings)!=1:reasons.append('ambiguous_analysis')
  else:
   reading=readings[0];tags=re.findall(r'<([^<>]+)>',reading)
   if tags not in [['adv'],['adv','pos']]:reasons.append('nonbase_or_operator_analysis_unqualified')
   if norm(reading.split('<',1)[0])!=norm(form['headword']):reasons.append('analysis_lemma_not_form_headword')
 return sorted(set(reasons))
def term_reasons(s,t):
 reasons=list(s['reasons'])+list(t['reasons'])
 if not s['eligible'] or not t['eligible']:reasons.append('term_ineligible')
 if not s['explicit'] or not t['explicit']:reasons.append('nonexplicit_relation')
 if s['sense_id']!=t['sense_id']:reasons.append('no_shared_retained_link')
 return sorted(set(reasons))
def controls():
 f={'reasons':[],'pos':'adv','complete':True,'mode':1,'features':[],'surface':'calmly','headword':'calmly','number':0};r={'chosen_roles':['ADV'],'unknown':False,'joined_morphemes':False,'readings':['calmly<adv>']}
 assert not base_reasons(f,r)
 for g in [dict(f,reasons=['dictionary_guard']),dict(f,features=['comparative']),dict(f,complete=False),dict(f,pos='adj')]:assert base_reasons(g,r)
 for g in [dict(r,chosen_roles=['ADJ']),dict(r,unknown=True),dict(r,readings=['calmly<adv><cmp>']),dict(r,readings=['calmly<adv><itg>'])]:assert base_reasons(f,g)
 # Number is deliberately not used to approve an adverb.
 assert base_reasons(dict(f,number=9),r)==base_reasons(f,r)
 t={'reasons':[],'eligible':True,'explicit':True,'sense_id':'retained'};assert not term_reasons(t,t);assert term_reasons(t,dict(t,explicit=False))
 return True
