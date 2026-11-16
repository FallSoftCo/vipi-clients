"""Bounded POS inventory from retained native tags, no translated output read."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TAG=ROOT/'qa/macos/apple-resume-20261116-r01/nltagger-r17.json'
FIX=ROOT/'qa/immersion/local-translation-feasibility-r01/fixtures.json'
OUT=Path(__file__).with_name('inventory-apple-english.json')
IDS=['local-01','local-02','local-03','local-04','local-05','local-06','local-18']
# Explicit conservative exclusions frozen before this inventory: closed-class
# auxiliary/modal tokens and weekdays. This is not a complete proper-name/NER guard.
AUX={'am','will','could'};WEEKDAYS={'monday','tuesday','wednesday','thursday','friday','saturday','sunday'}
def digest(b):return hashlib.sha256(b).hexdigest()
def from_u16(text,a,b):return text.encode('utf-16-le')[2*a:2*b].decode('utf-16-le')
tb=TAG.read_bytes();fb=FIX.read_bytes();tags={r['id']:r for r in json.loads(tb)['cases']};source={r['id']:r for r in json.loads(fb)['cases']};rows=[]
for id in IDS:
 t=tags[id];f=source[id];assert t['original']==f['original'] and t['source']==f['source_language']=='en';attempts=[]
 for i,token in enumerate(t['tags']):
  if token['lexical_class'] not in ('Noun','Verb'):continue
  a,b=token['start_utf16'],token['end_utf16'];surface=token['text'];assert from_u16(t['original'],a,b)==surface
  reason='explicit_auxiliary_or_modal' if surface.casefold() in AUX else 'weekday_proper_name' if surface.casefold() in WEEKDAYS else None
  attempts.append({'id':f'{id}-tag-{i:02d}','start_utf16':a,'end_utf16':b,'surface':surface,'raw_pos':token['lexical_class'],'preregistered_rejection':reason,'native_geometry_check':'pending actual consumer','protected_literal_check':'pending actual consumer'})
 rows.append({'id':id,'source_language':'en','target_language':f['target_language'],'original':t['original'],'pos_candidates':attempts})
result={'schema':'vipi-actual-pos-candidate-inventory-1','scope':'Exposed authored messages, actual retained macOS NLTagger lexical-class annotations; no target output used to choose candidates. Apple inventory only; Android must generate independently. Not a holdout, safe-translation or iOS support claim.','inputs':{'native_tag_file_sha256':digest(tb),'source_fixture_sha256':digest(fb)},'preregistered_policy':{'scope':'All recorded noun/verb tags; no authored winners','excluded_auxiliary_or_modal_exact_case_insensitive':sorted(AUX),'excluded_weekdays_exact_case_insensitive':sorted(WEEKDAYS),'native_word_geometry_and_existing_literal_masks':'required on actual platform; retain all accepted and rejected records','noun_verb_conflicts':'abstain pending qualified resolver','phrases':'omitted: no actual syntactic-unit boundary evidence in retained NLTagger run','output_selection':'freeze all admitted whole-unit attempts before translation; preserve every result and grade every emission'},'rows':rows}
OUT.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print('messages',len(rows),'noun_verb_occurrences',sum(len(r['pos_candidates']) for r in rows),'preregistered_rejections',sum(c['preregistered_rejection'] is not None for r in rows for c in r['pos_candidates']),'sha256',digest(OUT.read_bytes()))
