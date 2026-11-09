"""Preparation only: support census and overlap with retained outputs, no new selections."""
from common import *
import sqlite3,zlib

def main(r):
 r.verify();cat=sqlite3.connect(r.paths['catalog'].as_uri()+'?mode=ro&immutable=1',uri=True);cat.row_factory=sqlite3.Row;new={};baseline={}
 for row in cat.execute('select * from heads where baseline=1 or experimental=1'):
  record=json.loads(row['record']);audit=json.loads(row['audit']);assert not audit['experimental_competing_geometry'] if row['baseline'] else True
  if row['baseline']:baseline[row['id']]=record
  else:new[row['id']]={'record':record,'audit':audit,'links':{tuple(m[k] for k in ['source_form_id','target_form_id','source_term_id','target_term_id']) for m in audit['override_links']}}
 assert len(baseline)==2556 and len(new)==1480;data=json.loads(r.paths['dataset'].read_text());train=[x for x in data['rows'] if x['pool']=='explicit' and x['split']=='train'];assert len(train)==2987;comp_splits=collections.defaultdict(set);text_splits=collections.defaultdict(set)
 for x in data['rows']:comp_splits[x['component']].add(x['split']);text_splits[norm(data['endpoints'][x['endpoint']]['text'])].add(x['split'])
 assert all(len(v)==1 for v in comp_splits.values()) and all(len(v)==1 for v in text_splits.values());db=sqlite3.connect(r.paths['evidence'].as_uri()+'?mode=ro&immutable=1',uri=True);sizes=collections.Counter((x['key'],x['component']) for x in train);patterns={};rows={};rejections=collections.Counter();headkeys=collections.defaultdict(set)
 for x in train:
  e=data['endpoints'][x['endpoint']];assert [(t['text'],*t['codepoints']) for t in e['tokens']]==r.tokenize(e['text']);values=[norm(t['text']) for t in e['tokens']];i=x['focus_index'];assert e['tokens'][i]['utf16']==x['span'];valid=collections.defaultdict(lambda:collections.defaultdict(set))
  for face,target in x['targets'].items():
   for ref in target['relation_refs']:
    d=json.loads(db.execute('select data from objects where id=?',(ref,)).fetchone()[0]);assert d['stratum']=='old_explicit_shared_link' and d['original_form_number_term_eligible'] and d['both_exact_form_roles_noun'] and not d['exact_focus_reasons'] and not d['original_envelope_reasons'];hid=d['head']
    if hid not in new:rejections['head_not_original_new_eligible']+=1;continue
    sf=data['dictionary_forms'][d['source_form_ref']];tf=data['dictionary_forms'][d['target_form_ref']];link=(sf['form_id'],tf['form_id'],d['source_term']['term_id'],d['target_term']['term_id'])
    if face!=new[hid]['record']['target_face'] or link not in new[hid]['links']:rejections['not_exact_original_face_and_override_link']+=1;continue
    valid[face][hid].add(ref);headkeys[hid].add(x['key'])
  rows[x['id']]={'key':x['key'],'endpoint':x['endpoint'],'span':x['span'],'component':x['component'],'pair_ids':x['pair_ids'],'valid_heads_by_face':{f:{h:sorted(ids) for h,ids in hs.items()} for f,hs in valid.items()},'all_observed_faces':sorted(x['targets'])}
  weight=1/(sizes[(x['key'],x['component'])]*len(x['targets']))
  for key,a,b in windows(x['key'],values,i):
   p=patterns.setdefault(key,{'key':key,'source_key':x['key'],'length':b-a,'focus_offset':i-a,'tokens':values[a:b],'counts':collections.Counter(),'components':collections.defaultdict(set),'rows':collections.defaultdict(set),'head_rows':collections.defaultdict(lambda:collections.defaultdict(set))})
   for face in x['targets']:
    p['counts'][face]+=weight;p['components'][face].add(x['component']);p['rows'][face].add(x['id'])
    for hid in valid.get(face,{}):p['head_rows'][face][hid].add(x['id'])
 table={};rejected=collections.Counter();census=hashlib.sha256();totalencoded=0
 for key,p in sorted(patterns.items()):
  ordered=sorted(p['counts'],key=lambda f:(-p['counts'][f],f));winner=ordered[0];mass=p['counts'][winner];runner=p['counts'][ordered[1]] if len(ordered)>1 else 0;why=[]
  if len(ordered)>1 and abs(mass-runner)<=1e-12:why.append('tie')
  if mass<=1.5*runner+1e-12:why.append('margin')
  if len(p['components'][winner])<2:why.append('under_two_components')
  heads={hid:sorted(ids) for hid,ids in p['head_rows'][winner].items() if len({rows[i]['component'] for i in ids})>=2}
  record={'id':digest(key),'source_key':p['source_key'],'length':p['length'],'focus_offset':p['focus_offset'],'tokens':p['tokens'],'target':winner,'winner_weight':mass,'runner_weight':runner,'ratio':mass/runner if runner else None,'winner_components':len(p['components'][winner]),'weighted_counts':dict(p['counts']),'support_rows':{f:sorted(ids) for f,ids in p['rows'].items()},'support_components':{f:sorted(ids) for f,ids in p['components'].items()},'admissible_head_rows':heads,'unavailable_original_face_or_head_support':not heads,'reasons':why};raw=enc([key,record]).encode();census.update(raw+b'\n');totalencoded+=len(raw)
  if why:rejected.update(why)
  else:table[key]=record
 # Overlap uses only already frozen trace candidates/decisions, never new selections.
 overlap=collections.Counter();byknown=collections.defaultdict(collections.Counter);seen=[];prospective_project_bound=0; schema_bound_bytes=0; compressed_schema_bytes=0; compressor=zlib.compressobj(6,zlib.DEFLATED,31)
 with gzip.open(r.paths['trace'],'rt') as f:
  for line in f:
   t=json.loads(line);seen.append(t['id']);cs=t['candidates'];n=t['baseline_candidate_count'];assert not t['competition_removed_baseline_indices'];base=[c for c in cs[:n] if not c['filter_reasons']];adds=[c for c in cs[n:] if not c['filter_reasons']];bf={tuple(c['focus_utf16']) for c in base};bi={enc([c['focus_utf16'],c['target'],c['reading']]) for c in base};overlap['messages']+=1;overlap['baseline_candidates']+=len(base);overlap['exception_candidates']+=len(adds);overlap['messages_with_exception_candidates']+=bool(adds);overlap['baseline_unique_focuses']+=len(bf);af={tuple(c['focus_utf16']) for c in adds};overlap['exception_unique_focuses']+=len(af);overlap['exception_focuses_absent_baseline_candidates']+=len(af-bf);overlap['messages_with_absent_focus']+=bool(af-bf)
   for c in adds:overlap['exception_same_focus_existing_target_reading']+=enc([c['focus_utf16'],c['target'],c['reading']]) in bi;overlap['exception_same_focus_different_or_absent_face']+=tuple(c['focus_utf16']) in bf and enc([c['focus_utf16'],c['target'],c['reading']]) not in bi
   for known,v in t['decisions'].items():
    b=v['baseline'];e=v['experimental'];bc=byknown[known];bc['baseline_nonempty']+=bool(b['selected_indices']);bc['unrestricted_nonempty']+=bool(e['selected_indices']);bc['existing_empty_gains']+=not b['selected_indices'] and bool(e['selected_indices']);bc['existing_empty_losses']+=bool(b['selected_indices']) and not e['selected_indices']
   prospective_project_bound+=len(line.encode())+len(enc(t['decisions']).encode())+len(cs)*4096
   # Serialize an explicit output-schema superset without evaluating a context gate or selector.
   groups=collections.defaultdict(list)
   for j,c in enumerate(cs[n:],n):
    if not c['filter_reasons']:groups[enc(c['focus_utf16'])].append(j)
   maximum=max([len(enc(v['target']).encode()) for v in table.values()]+[1]);extent=len(t['text'].encode('utf-16-le'))//2;ga={}
   for focus,ids in groups.items():
    keys={k for j in ids for k in headkeys.get(cs[j]['head_id'],set())};matches=[{'id':digest([focus,key,z]),'tokens':[0,extent],'utf16':[0,extent],'target':'x'*maximum} for key in keys for z in range(35)]
    ga[focus]={'candidate_indices':ids,'admitted_indices':ids,'chosen_rule_id':'f'*64,'chosen_context_utf16':[0,extent],'chosen_source_tokens':[0,extent],'matched_rules':matches,'reason':'winner_without_original_supported_head'}
   # All index arrays and all rejection labels deliberately over-bound any actual selector output.
   reasonlabels=['focus_outside_context','partial_native_word','not_exact_native_boundaries','invalid_candidate_id','invalid_concept_id','invalid_category','invalid_train_rank','empty_or_invalid_target','invalid_identity_flag','identical_face','invalid_knowledge_ids','known_function','known_vocabulary','protected_focus','inside_recognized_source_unit','malformed_candidate','repeated_concept','over_total_budget','overlap','exceeds_remaining_budget']
   dec={'selected_indices':list(range(len(cs))),'pre_budget_indices':list(range(len(cs))),'budget_only_indices':list(range(len(cs))),'budget':max(1,len(t['native_words_utf16'])),'rejected':[{'index':j,'reasons':reasonlabels} for j in range(len(cs))],'mixed_output':t['text']+'x'*sum(len(c['target'].encode()) for c in cs)};preview={'id':t['id'],'gates':ga,'qualified':{k:dec for k in KNOWN},'retained_trace_sha256':r.p['inputs']['trace']['sha256']};encoded=(enc(preview)+'\n').encode();schema_bound_bytes+=len(encoded);compressed_schema_bytes+=len(compressor.compress(encoded))

 compressed_schema_bytes+=len(compressor.flush());assert len(seen)==9535 and len(set(seen))==9535
 r.write('lookup.json',{'rules':table,'head_keys':{h:sorted(v) for h,v in headkeys.items()},'train_rows':rows,'original_head_records':{h:v['record'] for h,v in new.items()},'original_override_links':{h:sorted(v['links']) for h,v in new.items()},'no_direct_candidates':True});r.write('overlap.json',{'candidate_overlap':dict(overlap),'existing_decision_counts':{k:dict(v) for k,v in byknown.items()},'limits':'Pre-budget candidate overlap vs unchanged broad baseline and retained unrestricted outputs only; no context-qualified predictions. Candidate/occurrence/message counts differ.','source_ID_order_sha256':digest(seen)});r.write('support-summary.json',{'train_rows':len(train),'all_patterns':len(patterns),'qualified_context_patterns':len(table),'qualified_with_original_head_support':sum(bool(v['admissible_head_rows']) for v in table.values()),'overlapping_rejections':dict(rejected),'link_binding_rejections':dict(rejections),'full_pattern_census_sha256':census.hexdigest(),'full_pattern_encoded_bytes_if_materialized':totalencoded,'lookup_exact_bytes':(r.out/'lookup.json').stat().st_size,'rough_conservative_trace_plus_4096_estimate_not_measurement':prospective_project_bound,'encoded_projector_schema_superset_bytes':schema_bound_bytes,'schema_superset_gzip_bytes_not_physical_guarantee':compressed_schema_bytes,'default_and_train_split_unchanged':True,'counts_only_no_new_selections':True})
 db.close();cat.close()
if __name__=='__main__':
 r=Run('prepare')
 try:main(r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
