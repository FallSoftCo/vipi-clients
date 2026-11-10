#!/usr/bin/env python3
"""Freeze finite source controls before any native output, no target gold."""
from pathlib import Path
import json,hashlib
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');P=W/'preparation-r01'
contrasts=[
('slots','I would like a mailing address for the parcel.'),('slots','She needs a doctor before dinner.'),('slots','We wanted some rest after the walk.'),('slots','He sends the message before lunch.'),
('negation','I do not need a taxi today.'),('negation','She is not looking for a hotel.'),
('long_short_overlap','I need a phone charger before the trip.'),('long_short_overlap','We need a phone charger and your phone number.'),('multiword','Meet me at the train station after lunch.'),('multiword','I need a door key and a train ticket.'),
('repetition','I need help, and my friend needs help too.'),('repetition','The phone charger is beside another phone charger.'),
('name_outside_focus','I am looking for a hotel called Apple.'),('name_outside_focus','My dog is named Party.'),('quoted','She wrote `need a doctor` in the file.'),('quoted','The label says "bank account".'),
('literal','I am drinking coffee_today.txt now.'),('literal','Meet me at the train station.txt tomorrow.'),('prefix_word','I need a doctorate before applying.'),('prefix_word','I need a phone chargersaurus for the play.'),
('punctuation_barrier','I need a. Doctor Smith called.'),('punctuation_barrier','We talked about the train. Station staff arrived.'),('newline_barrier','I need a\ndoctor tomorrow.'),('partial_prefix','They dislike music during meetings.'),
('conflicting_use','Please help me carry the bag.'),('conflicting_use','I gave an account of the river bank.'),('conflicting_use','The hotel room service arrived.'),('bare_unlicensed','A phone charger is missing.'),
('identical_face','I am playing the piano now.'),('retained_case','The birthday party starts after lunch.'),('retained_case','Please send your phone number before dinner.'),('longest_small_budget','Need a phone charger.'),
('longest_small_budget','I need a train ticket.'),('enclosing_literal','Use https://example.com/phone_charger and read a book.'),('ordinary_multiple','I am reading a book and drinking tea before bed.'),('separate_context','I need a taxi. The receipt is in my pocket.')]
def main():
 dst=W/'cases-r01';assert not dst.exists();dst.mkdir();original=json.loads((P/'original-source-cases.json').read_text());cases=[];groups={}
 for x in original:
  key=(x['pair'],x['source']);groups.setdefault(key,[]).append(x)
 for (pair,source),rs in sorted(groups.items()):cases.append({'id':'seed-'+hashlib.sha256((pair+'\0'+source).encode()).hexdigest()[:20],'pair':pair,'source':source,'stratum':'original_seed_context','exposure':'Retained authored bidirectional development source, not fresh holdout.','pattern_ids':sorted({r['pattern_id'] for r in rs}),'record_bindings':[{'id':r['original_record_id'],'focus_utf16':r['expected_focus_utf16']} for r in rs]})
 for pair in ['en-ja','en-sw']:
  for i,(stratum,source) in enumerate(contrasts):cases.append({'id':f'control-{i+1:02d}','pair':pair,'source':source,'stratum':stratum,'exposure':'Authored pre-output diagnostic; design/root-specified failure modes exposed; no claimed fresh corpus generalization.','pattern_ids':[],'record_bindings':[]})
 # Source-only exact duplicates remain explicitly separate design strata.
 (dst/'sources.json').write_text(json.dumps({'schema':1,'cases':cases,'density_states':[0.25,0.75],'extra_density_controls':{'control-32':[0.0,0.05],'control-33':[0.0,0.05]},'known_states':['none','all_current_starter_concepts_excluded'],'known_state_semantics':'Exact exclusions, not familiarity or mastery; same for baseline/candidate.','native_execution':False},ensure_ascii=False,indent=2)+'\n')
 receipt={'source_sha256':hashlib.sha256((dst/'sources.json').read_bytes()).hexdigest(),'compiler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_record_contexts':len(original),'unique_original_source_pairs':len(groups),'authored_controls_per_pair':len(contrasts),'source_pair_cases':len(cases),'input_sha256':hashlib.sha256((P/'original-source-cases.json').read_bytes()).hexdigest(),'new_native_predictions_seen':False,'existing_seed_target_faces_seen':True};(dst/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
if __name__=='__main__':main()
