#!/usr/bin/env python3
"""TRAIN-only dictionary consensus audit; no unreviewed data can enter the apps."""
import argparse,collections,gzip,hashlib,json,math,re,sqlite3,time,unicodedata
from pathlib import Path
from evaluate_source_concepts import candidates as guarded_candidates
Q=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return unicodedata.normalize('NFKC',s).casefold().replace('’',"'").strip()
def glossnorm(s):return re.sub(r'[^\w\s]','',norm(s)).strip()
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--source-inventory',type=Path,required=True);p.add_argument('--native-senses',type=Path,required=True);p.add_argument('--source-db',type=Path,required=True);p.add_argument('--candidate-db',type=Path,required=True);p.add_argument('--target-metadata',type=Path,required=True);p.add_argument('--train',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(exist_ok=False);started=time.monotonic();policy=json.loads((Q/'scaled-consensus-policy-r02.json').read_text());source=json.loads(a.source_inventory.read_text());native=json.loads(gzip.decompress(a.native_senses.read_bytes()));assert native['complete'];assert sha(a.train)=='a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c'
 rawentries={r[0]:r for r in native['entries']};rawsenses=collections.defaultdict(list)
 for r in native['senses']:rawsenses[r[0]].append(r)
 excluded=set(policy['native_excluded_tags']);closed=set(policy['closed_class_source_forms']);sdb=ro(a.source_db);links=collections.defaultdict(dict)
 for lex,sid,label,pos,explicit,eligible,qual in sdb.execute('SELECT t.lexeme,t.sense,s.label,s.pos,s.explicit,t.eligible,t.qualifiers FROM terms t JOIN senses s ON s.id=t.sense'):
  if lex in rawentries and explicit:
   prior=links[lex].get(sid);usable=bool(eligible) and qual=='{}'
   if not prior or usable:links[lex][sid]={'label':label,'pos':pos,'eligible':usable,'qualifiers':qual}
 sdb.close();tm=json.loads(gzip.decompress(a.target_metadata.read_bytes()));assert tm['candidate_sha256']==sha(a.candidate_db);cdb=ro(a.candidate_db);target=collections.defaultdict(lambda:collections.defaultdict(set));rawtarget=collections.defaultdict(set);languages=set();target_filters=collections.defaultdict(collections.Counter);filtered_sources=collections.defaultdict(lambda:collections.defaultdict(set))
 for r in cdb.execute('SELECT source,source_lexeme,sense,target_language,target_lexeme,target,reading,legacy_source_eligible,legacy_target_eligible,source_qualifiers,target_qualifiers,complete_target_head,reading_present,pos_compatible FROM candidates'):
  w,lex,sid,lang,tlex,face,reading,se,te,sq,tq,whole,rd,pos=r;languages.add(lang);rawtarget[(w,lang)].add(sid)
  reason='not_native_lexical_target' if not tm['targets'][lang][str(tlex)]['target_lexical_safe'] else 'contradicted_or_qualified_link' if not(se and te and sq=='{}' and tq=='{}') else 'incomplete_target_head' if not whole else 'reading_missing' if not rd else 'POS_mismatch' if not pos else 'unchanged_face' if norm(w)==norm(face) else None
  if reason:target_filters[lang][reason]+=1;filtered_sources[lang][reason].add(w)
  else:target[(w,lang)][(lex,sid)].add((face,reading))
 cdb.close();source_part=collections.Counter();rows=[];familyfreq=collections.Counter()
 for r in source['rows']:
  w=r['source'];active=[];source_rejections=[]
  for l in r['content_lexemes']:
   lex=l['lexeme'];raw=rawentries[lex];head=raw[2];pos=raw[4];etags=set(json.loads(raw[5]));glosses=set()
   if head!=head.lower():source_rejections.append((lex,'capitalized_name_or_initial_head'));continue
   if etags&excluded:source_rejections.append((lex,'excluded_native_entry_tag'));continue
   for sense in rawsenses[lex]:
    tags=set(json.loads(sense[3]));gs=json.loads(sense[2]);forms=json.loads(sense[4]);alts=json.loads(sense[5])
    if tags&excluded or forms or alts or tags&{'form-of','alt-of'} or not gs:continue
    glosses.add(gs[-1])
   if not glosses:source_rejections.append((lex,'no_active_lexical_definition'));continue
   groups=links[lex];groupnorm={glossnorm(g['label']) for g in groups.values() if g['eligible'] and g['qualifiers']=='{}'};covered={g for g in glosses if glossnorm(g) in groupnorm};single=len(glosses)==1 and bool(groups)
   full_native=bool(groups) and (single or len(covered)==len(glosses));direct=norm(head)==w;alternative=any(norm(surface)==w and 'alternative' in json.loads(features) for surface,features,number in l['complete_surfaces']);formkind='canonical' if direct else 'explicit_alternative' if alternative else 'inflected_or_other'
   active.append({'lexeme':lex,'head':head,'pos':pos,'modern_native_glosses':sorted(glosses),'native_glosses_count':len(glosses),'explicit_groups':groups,'exact_label_covered_glosses':sorted(covered),'single_definition_group_evidence':single,'native_sense_evidence_complete':full_native,'form_kind':formkind})
  partition='closed_class_source_usage' if w in closed else 'no_active_content_entry' if not active else 'inflected_form_needs_realization' if any(e['form_kind']=='inflected_or_other' for e in active) else 'missing_English_translation_groups' if any(not e['explicit_groups'] for e in active) else 'native_sense_completeness_unresolved' if any(not e['native_sense_evidence_complete'] for e in active) else 'source_sense_evidence_complete'
  heads=sorted({e['head'] for e in active});family=heads[0] if len(heads)==1 else 'unresolved:'+w
  if len(heads)>1 and partition=='source_sense_evidence_complete':partition='source_family_grouping_unresolved'
  source_part[partition]+=1
  if len(heads)==1 and w not in closed:familyfreq[family]+=r['occurrences']
  rows.append({'source':w,'rank':r['rank'],'TRAIN_occurrences':r['occurrences'],'source_partition':partition,'family':family,'active_entries':active,'source_rejections':source_rejections,'targets':{}})
 learned=[k for k,v in sorted(familyfreq.items(),key=lambda t:(-t[1],t[0]))];summary={};lexicons={}
 for lang in sorted(languages):
  part=collections.Counter();strata=collections.Counter();potential=[];qualified=[]
  for r in rows:
   w=r['source'];active=r['active_entries'];groups=[(e['lexeme'],sid) for e in active for sid in e['explicit_groups']];sets=[target[(w,lang)].get(g,set()) for g in groups];missing=[g for g,v in zip(groups,sets) if not v];common=set.intersection(*sets) if sets and not missing else set();perpos={}
   for pos in sorted({e['pos'] for e in active}):
    gs=[(e['lexeme'],sid) for e in active if e['pos']==pos for sid in e['explicit_groups']];vs=[target[(w,lang)].get(g,set()) for g in gs];perpos[pos]=sorted(set.intersection(*vs)) if vs and all(vs) else []
   state='source_usage_or_form_unavailable' if r['source_partition'] in {'closed_class_source_usage','no_active_content_entry','inflected_form_needs_realization'} else 'source_groups_missing' if not groups or any(not e['explicit_groups'] for e in active) else 'target_group_evidence_missing' if missing else 'context_or_POS_required' if not common else 'linked_group_consensus_native_evidence_incomplete' if r['source_partition']!='source_sense_evidence_complete' else 'native_sense_supported_consensus'
   part[state]+=1;strata['forms_with_per_POS_consensus_before_source_guards']+=any(perpos.values());strata['forms_with_all_group_consensus_before_source_guards']+=bool(common)
   if state!='source_usage_or_form_unavailable':strata['forms_with_per_POS_consensus_after_source_usage_guards']+=any(perpos.values());strata['forms_with_all_group_consensus_after_source_usage_guards']+=bool(common)
   detail={'state':state,'explicit_group_count':len(groups),'missing_target_groups':missing,'target_consensus':[{'target':f,'reading':rd} for f,rd in sorted(common)],'per_pos_consensus':perpos};r['targets'][lang]=detail
   if common and state in {'linked_group_consensus_native_evidence_incomplete','native_sense_supported_consensus'}:
    face,rd=sorted(common,key=lambda x:(len(x[0]),x))[0];entry={'id':'consensus-en-'+lang+'-'+w,'source':w,'target':face,'reading':rd,'category':'content','pos':'+'.join(sorted(perpos)),'train_rank':r['rank'],'concept_id':r['family'],'evidence_stratum':state};potential.append(entry)
    if state=='native_sense_supported_consensus':qualified.append(entry)
  summary[lang]={'partition':dict(part),'strata':dict(strata),'potential_linked_consensus_forms':len(potential),'source_supported_consensus_forms':len(qualified),'target_row_rejections':dict(target_filters[lang]),'target_rejection_distinct_sources':{k:len(v) for k,v in filtered_sources[lang].items()}};lexicons[lang]={'linked_groups_only':{'entries':potential},'source_supported':{'entries':qualified}}
 cases=[]
 for ci,c in enumerate(json.loads(a.train.read_text())):
  if c['context_dataset']!='convai2':continue
  for ti,(speaker,text) in enumerate(c['dialog']):
   if speaker==0 and text.strip():cases.append((f'bst-train-{ci:04d}-{ti:02d}',text))
 metrics={};sample=[]
 for lang,arms in lexicons.items():
  for arm,lexicon in arms.items():
   byid={e['id']:e for e in lexicon['entries']}
   for cid,text in cases:
    tokens,spans,rejections=guarded_candidates(text,lexicon);n=len(tokens);length='1-5' if n<=5 else '6-15' if n<=15 else '16+'
    for s in spans:s['concept_id']=byid[s['lexicon_id']]['concept_id'];s['reading']=byid[s['lexicon_id']]['reading']
    for k in [0,50,100,300]:
     known=set(learned[:k]);eligible=sorted([s for s in spans if s['concept_id'] not in known],key=lambda s:(s['train_rank'],s['start']))
     for density in [.10,.25,.50]:
      chosen=[];seen=set();budget=max(1,math.floor(n*density))
      for s in eligible:
       if s['concept_id'] in seen:continue
       if len(chosen)>=budget:break
       chosen.append(s);seen.add(s['concept_id'])
      for view in ['all',length]:
       key=(lang,arm,k,density,view);m=metrics.setdefault(key,{'messages':0,'raw_messages_with_content':0,'source_words':0,'selected_content_words':0,'message_depth_sum':0.,'core_noun_verb_adjective_messages':0,'core_noun_verb_adjective_words':0,'core_depth_sum':0.,'core_families':set(),'selected_families':set(),'selected_POS':collections.Counter()});m['messages']+=1;m['raw_messages_with_content']+=bool(chosen);m['source_words']+=n;m['selected_content_words']+=len(chosen);m['message_depth_sum']+=len(chosen)/n if n else 0;m['selected_families'].update(seen);m['selected_POS'].update(s['pos'] for s in chosen);core=[s for s in chosen if set(s['pos'].split('+')) & {'noun','verb','adj'}];m['core_noun_verb_adjective_messages']+=bool(core);m['core_noun_verb_adjective_words']+=len(core);m['core_depth_sum']+=len(core)/n if n else 0;m['core_families'].update(s['concept_id'] for s in core)
      if density==.25 and k==0 and chosen and len([v for v in sample if v['language']==lang and v['arm']==arm])<12:
       sample.append({'id':cid,'text':text,'language':lang,'arm':arm,'spans':chosen,'rejections':rejections})
 outmetrics=[]
 for (lang,arm,known,density,view),m in metrics.items():
  m['mean_content_depth']=m.pop('message_depth_sum')/m['messages'];m['mean_core_content_depth']=m.pop('core_depth_sum')/m['messages'];m['distinct_core_families']=len(m['core_families']);m['core_families']=sorted(m['core_families']);m['token_weighted_content_depth']=m['selected_content_words']/m['source_words'];m['distinct_content_families']=len(m['selected_families']);m['selected_families']=sorted(m['selected_families']);m['selected_POS']=dict(m['selected_POS']);outmetrics.append(dict(language=lang,arm=arm,known_first=known,density=density,view=view,**m))
 result={'production':False,'semantic_approval':False,'training_only':True,'input_hashes':{str(p):sha(p) for p in [a.source_inventory,a.native_senses,a.source_db,a.candidate_db,a.target_metadata,a.train,Q/'scaled-consensus-policy-r02.json',Path(__file__)]},'source_partition':dict(source_part),'targets':summary,'concept_family_count':len(learned),'learned_family_order':learned,'source_rows':rows,'candidate_lexicons':lexicons,'TRAIN_messages':len(cases),'TRAIN_metrics':outmetrics,'first12_per_pair_arm_diagnostic_outputs':sample,'elapsed_seconds':time.monotonic()-started,'limits':['Raw eligible content reach and depth are not semantic accuracy or release coverage.','Linked-groups-only arm explicitly lacks complete native-source-sense evidence; not a qualified fallback.','Single native-definition+scoped translation-group evidence is separate from exact native-gloss/group-label coverage; both retained per entry.','No machine sense classifier, guessed morphology, provider translation, native boundary or pronunciation qualification.','TRAIN role-play frequency cannot be extrapolated to worldwide spontaneous chat.']};path=a.output_dir/'consensus-audit.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'source_partition':dict(source_part),'targets':summary,'elapsed':result['elapsed_seconds'],'output_sha256':sha(path)}),flush=True)
if __name__=='__main__':main()
