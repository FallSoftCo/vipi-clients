#!/usr/bin/env python3
"""TRAIN-only source-role capacity; no target face selection or semantic approval."""
import argparse, collections, hashlib, json, math, re, sqlite3, time
from pathlib import Path
from evaluate_reviewed_words import WORD, PROTECTED
from evaluate_source_concepts import DETERMINERS, PREPOSITIONS, OBJECT_VERBS
Q=Path(__file__).resolve().parent
COPULA=set('am is are was were be been being seem seems seemed feel feels felt look looks looked sound sounds sounded become becomes became'.split())
PRONOUN=set('i you he she it we they'.split())
DEGREE=set('very really quite so too more most less least pretty extremely rather especially fairly'.split())
AUX=set('do does did can could should would will may might must shall'.split())
NEG_AUX={"don't","doesn't","didn't","can't","couldn't","shouldn't","wouldn't","won't","cannot"}
ADVERBS=set('really always often sometimes usually never also still just probably certainly actually'.split())

def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def classify(text,tokens,i,pos_by_word):
 t=tokens[i];word=t.group().casefold().replace('’',"'")
 initial=not text[:t.start()].strip() or text[:t.start()].rstrip()[-1:] in '.!?'
 if any(m.start()<t.end() and t.start()<m.end() for m in PROTECTED.finditer(text)): return set(),'protected'
 if any(x in text for x in ('"','“','”','`')): return set(),'quoted_or_code'
 if t.group().isupper() and len(t.group())>1:return set(),'uppercase'
 if t.group()[0].isupper() and not initial:return set(),'mid_capital'
 left=i
 while left and not text[tokens[left-1].end():tokens[left].start()].strip():left-=1
 right=i+1
 while right<len(tokens) and not text[tokens[right-1].end():tokens[right].start()].strip():right+=1
 before=[x.group().casefold().replace('’',"'") for x in tokens[left:i]]
 after=[x.group().casefold().replace('’',"'") for x in tokens[i+1:right]]
 prev=before[-1] if before else None;nxt=after[0] if after else None
 roles=set()
 # Positive local role evidence, not a complete parser or sense classifier.
 if prev in DETERMINERS|PREPOSITIONS|OBJECT_VERBS or (initial and nxt in COPULA):roles.add('noun')
 if prev in COPULA|DEGREE or ('noun' in pos_by_word.get(nxt,set()) and prev in DETERMINERS|DEGREE):roles.add('adj')
 prefix=before[:]
 for _ in range(2):
  if prefix and prefix[-1] in ADVERBS|NEG_AUX|{'not'}:prefix.pop()
 subject=prefix[-1] if prefix and prefix[-1] in PRONOUN else None
 preceding=prefix[-2] if subject and len(prefix)>1 else None
 # General copular inversion rejection, shared by every verbal entry.
 if prev=='to' or (subject and preceding not in COPULA) or prev in AUX|NEG_AUX:roles.add('verb')
 if 'adv' in pos_by_word.get(word,set()) and (word.endswith('ly') or pos_by_word[word]=={'adv'}):roles.add('adv')
 return roles,'local_role_unresolved' if not roles else ''

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();E=a.evidence_dir
 paths={'audit':E/'scaled-consensus-r01/consensus-audit.json','source':E/'scaled-content-inventory-r01/source-inventory.json','targets':E/'scaled-content-inventory-r01/primary-candidates.sqlite','train':E/'bst-evaluation-source-r01/train.json','groups':Q/'role-content-candidate-r02.json','closed':Q/'scaled-consensus-policy-r02.json'}
 policy={'production':False,'target_selection':False,'semantic_approval':False,'purpose':'Measure reusable positive local source-role capacity across the entire ranked inventory before broader target selection; no surface emitted.','source_conditions':'Existing complete source mappings with active modern native noun/verb/adj/adv entries. Exclude closed-class usage reinterpretation. Keep canonical/explicit-alternative and inflected tiers separate. No all-senses agreement.','role_rules':'Frozen classify() implementation; positive local noun/adjective/verb/adverb clues with protected/capital boundaries. General preceding copula inversion guard applies to all verbs. Rules are an unqualified capacity hypothesis, not semantic gold.','target_conditions':'Existing complete target head, required reading, compatible POS, source lexical entry active. Retain competing targets/senses; target choice, ordinary-sense fit and inflection are unresolved.','knowledge':[0,50,100,300],'densities':[.1,.25,.5],'source_sha256':h(Path(__file__)),'inputs':{k:h(v) for k,v in paths.items()}}
 freeze=a.output.with_name('role-inventory-capacity-freeze-r01.json');freeze.write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n')
 started=time.monotonic();audit=json.loads(paths['audit'].read_text());src=json.loads(paths['source'].read_text());closed=set(json.loads(paths['closed'].read_text())['closed_class_source_forms']);groups=json.loads(paths['groups'].read_text());train=json.loads(paths['train'].read_text());ranks={r['source']:r['rank'] for r in src['rows']}
 active={};pos_by_word={};tiers={};partition=collections.Counter()
 for row in audit['source_rows']:
  word=row['source'];entries=[e for e in row['active_entries'] if e['pos'] in {'noun','adj','verb','adv'}]
  if word in closed:partition['closed_class_usage']+=1;continue
  if not entries:partition['no_active_modern_content_entry']+=1;continue
  active[word]={e['lexeme']:e for e in entries};pos_by_word[word]={e['pos'] for e in entries}
  tiers[word]={e['pos']:{e['form_kind'] for e in entries if e['pos']==p} for p in pos_by_word[word] for e in entries if e['pos']==p}
  partition['active_nonclosed_content_surface']+=1
 db=sqlite3.connect(paths['targets'].resolve().as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;links=collections.defaultdict(lambda:collections.defaultdict(set));target_forms=collections.defaultdict(set)
 for r in db.execute('SELECT source,source_lexeme,source_pos,target_language,complete_target_head,reading_present,pos_compatible FROM candidates'):
  w=r['source']
  if w not in active or r['source_lexeme'] not in active[w] or not all(r[k] for k in ['complete_target_head','reading_present','pos_compatible']):continue
  links[w][r['source_pos']].add(r['target_language']);target_forms[r['target_language']].add(w)
 db.close();languages=sorted(target_forms);cases=[(f'bst-train-{ci:04d}-{ti:02d}',text) for ci,c in enumerate(train) if c['context_dataset']=='convai2' for ti,(speaker,text) in enumerate(c['dialog']) if speaker==0 and text.strip()]
 metrics={};observed=collections.defaultdict(set);form_counts=collections.Counter();role_counts=collections.Counter();examples=collections.defaultdict(list)
 for cid,text in cases:
  tokens=list(WORD.finditer(text));spans=[]
  for i,t in enumerate(tokens):
   w=t.group().casefold().replace('’',"'")
   if w not in active:continue
   roles,reason=classify(text,tokens,i,pos_by_word);admitted=roles&pos_by_word[w]
   for pos in admitted:
    role_counts[pos]+=1;form_counts[w]+=1;observed[pos].add(w)
    if len(examples[pos])<12:examples[pos].append({'id':cid,'text':text,'word':w,'pos':pos})
   if admitted:spans.append((t,w,admitted))
  for language in languages:
   for tier in ['canonical_or_alternative','including_attested_inflection']:
    eligible=[]
    for t,w,poses in spans:
     good=[p for p in poses if language in links[w].get(p,set()) and (tier=='including_attested_inflection' or tiers[w][p]&{'canonical','explicit_alternative'})]
     if good:eligible.append((t,w,good))
    for known in policy['knowledge']:
     learned=set(groups['learned_family_order'][:known]);remaining=[x for x in eligible if (groups['source_families'].get(x[1]) or x[1]) not in learned]
     for density in policy['densities']:
      budget=max(1,math.floor(len(tokens)*density));chosen=[];seen=set()
      for t,w,poses in sorted(remaining,key=lambda x:(ranks[x[1]],x[0].start())):
       family=groups['source_families'].get(w) or w
       if family in seen:continue
       chosen.append((t,w,poses,family));seen.add(family)
       if len(chosen)==budget:break
      key=(language,tier,known,density);m=metrics.setdefault(key,{'messages':0,'raw_available':0,'words':0,'changed':0,'depth_sum':0,'forms':set(),'concepts':set()});m['messages']+=1;m['raw_available']+=bool(chosen);m['words']+=len(tokens);m['changed']+=len(chosen);m['depth_sum']+=len(chosen)/len(tokens) if tokens else 0;m['forms'].update(x[1] for x in chosen);m['concepts'].update(x[3] for x in chosen)
 rows=[]
 for key,m in metrics.items():
  lang,tier,known,density=key;rows.append({'language':lang,'tier':tier,'known_global_content':known,'density':density,'messages':m['messages'],'raw_available':m['raw_available'],'message_mean_depth':m['depth_sum']/m['messages'],'word_weighted_depth':m['changed']/m['words'],'distinct_selected_forms':len(m['forms']),'distinct_selected_concepts':len(m['concepts']),'selected_forms':sorted(m['forms'],key=ranks.get)})
 out={'production':False,'target_selection':False,'semantic_approval':False,'freeze_sha256':h(freeze),'source_surface_denominator':3000,'linked_content_surface_denominator':2646,'source_partition':dict(partition),'active_content_surface_count':len(active),'positive_role_observed_forms':len(set().union(*observed.values())),'by_pos':{p:{'forms':len(v),'occurrences':role_counts[p]} for p,v in observed.items()},'target_link_potential_forms':{l:len(v) for l,v in target_forms.items()},'metrics':rows,'first_diagnostic_examples':dict(examples),'elapsed_seconds':time.monotonic()-started,'limits':['Raw local-role capacity is not actual target selection or correct immersion coverage.','Canonical target head may not realize source plural/tense; inflected tier is an upper potential requiring attested target morphology.','All 9535 TRAIN role-play messages; no heldout reused as training.','Competing ordinary senses and target commonness remain unresolved; no shortest-string or global all-sense intersection.']};a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['source_partition','positive_role_observed_forms','by_pos','target_link_potential_forms','elapsed_seconds']},ensure_ascii=False));print('sha256',h(a.output))
if __name__=='__main__':main()
