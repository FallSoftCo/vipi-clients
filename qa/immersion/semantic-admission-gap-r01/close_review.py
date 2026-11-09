"""Local, read-only result accounting; no predictions or label harmonization."""
import collections,hashlib,json,pathlib
W=pathlib.Path('/home/ai/Development/investigations/vipi-semantic-admission-gap-20261109-r01');Q=pathlib.Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
r=read(W/'outputs-r02/receipt.json')
for n,v in r['outputs'].items():
 p=W/'outputs-r02'/n;assert sha(p)==v['sha256'] and p.stat().st_size==v['bytes']
# Additive exposed-output judgments. Original independently frozen reviews are unchanged.
judgments={
 ('007','here'):('valid','Locative aquí preserves the current here.'),
 ('007','too'):('material_error','Current too adds agreement with the other location; demasiado introduces excessive degree.'),
 ('008','football'):('ambiguous_valid_reading','Fútbol is valid for association football; this source alone does not settle football variety.'),
 ('009','different'):('mixed_grammar_form_only','Different meaning preserved; plural diferentes beside irregular English singular kind is a form issue.'),
 ('010','just'):('uncertain','Temporal/restrictive readings overlap pragmatically. Retained solo temporal evidence prevents treating this as proven material error; capitalization separate.'),
 ('010','exercise'):('valid','Exercise video supports exercise/ejercicio; noun polysemy is not a current error.'),
 ('011','station'):('valid','Estación is an acceptable regional radio-station term in the top40 context.'),
 ('012','plane'):('valid_same_output_switch','Exact avión/focus is unchanged; only supporting candidate/context changes.'),
 ('014','beauty'):('valid','A beauty of a car supports belleza figuratively in mixed English syntax.'),
 ('015','Just'):('mixed_grammar_form_only','Restrictive sólo for a little while is plausible; initial capitalization differs.'),
 ('015','unfortunately'):('mixed_grammar_form_only','Desafortunadamente preserves meaning; mid-sentence capital is formatting only.'),
 ('016','just'):('mixed_grammar_form_only','Restrictive/imperative Solo dont tell is plausible mixed vocabulary; capital is separate.'),
 ('016','eggs'):('valid','Making husband eggs supports huevos.'),
 ('018','definitely'):('valid','Definitely/definitivamente preserves the recommendation emphasis.'),
 ('020','help'):('valid_same_output_switch','Exact ayuda/focus unchanged; only supporting context changes.'),
 ('023','just'):('material_error','They just test you is emphatic/restrictive; Apenas implies barely/as soon as, changing force.'),
 ('025','food'):('valid_same_output_switch','Exact comida/focus unchanged; only supporting context changes.')}
rows=[];counts=collections.Counter();unique={};sameface_switches=0
for x in read(W/'outputs-r02/native52.json'):
 for state,v in x['states'].items():
  for side in ['lost','added']:
   for i in v[side+'_indices']:
    c=x['candidates'][i];label,reason=judgments[(x['id'][-3:],c['source'])];other=v['added_indices' if side=='lost' else 'lost_indices'];same=any((x['candidates'][j]['focus_utf16'],x['candidates'][j]['target'],x['candidates'][j]['reading'])==(c['focus_utf16'],c['target'],c['reading']) for j in other)
    row={'case_id':x['id'],'known':state,'side':side,'candidate_index':i,'head_id':c['head_id'],'focus_utf16':c['focus_utf16'],'source':c['source'],'target':c['target'],'source_key':c['source_key'],'same_emission_other_candidate':same,'additive_label':label,'rationale':reason};rows.append(row);counts[state+'|'+side+'|'+label]+=1
    if side=='lost' and not same:unique[(x['id'],tuple(c['focus_utf16']),c['target'])]=label
    if side=='added' and same:sameface_switches+=1
out={'basis':'Exposed actual52 diagnosis by one agent; no independent accuracy/gold claim. Earlier frozen reviews untouched.','events':rows,'event_counts':dict(counts),'unique_lost_emissions_excluding_same_output_switches':dict(collections.Counter(unique.values())),'same_output_candidate_switches_across_states':sameface_switches,'all_added_events_are_same_output_switches':all(x['same_emission_other_candidate'] for x in rows if x['side']=='added')}
(W/'changed-emission-review-r01.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
receipt={'complete':True,'decision':'reject_as_final_admission_policy','experiment_rerun':False,'output_hashes_verified':True,'original_reviews_modified':False,'activation':False,'actual_review':{'events':len(rows),'unique_lost_emissions':len(unique),'same_output_candidate_switches_across_states':sameface_switches},'experiment_resources':{'seconds':r['seconds'],'VmHWM_bytes':r['VmHWM_bytes']},'source_files':{p.name:sha(p) for p in Q.iterdir() if p.is_file() and p.name!='completion-receipt.json'},'private_files':{str(p.relative_to(W)):sha(p) for p in W.rglob('*') if p.is_file()},'read_only_dictionary_audit':'738 exact lexeme IDs; frozen dictionary identity, no fresh whole-file rehash. Published sense count explains prevalence; flags do not establish current intent.'}
(Q/'completion-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'unique_lost':out['unique_lost_emissions_excluding_same_output_switches'],'events':len(rows),'same_output_switches':sameface_switches},indent=2))
