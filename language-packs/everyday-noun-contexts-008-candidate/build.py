"""Build a private context-only proposal from accepted sense-bound mappings.
No target invention, casing transform, morphology stripping, or runtime activation.
"""
import copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).parent
# Explicit noun constructions: targets and readings are copied from exact accepted
# directional records. These authored permission hypotheses require native QA.
CONTEXTS={
'en':{'needs_breakfast':['for breakfast','my breakfast','breakfast is'], 'phrase_frame_drinking_coffee':['a cup of coffee','some coffee','coffee is hot'], 'needs_water':['a glass of water','some water','bottled water']},
'es':{'needs_breakfast':['el desayuno','mi desayuno'], 'phrase_frame_drinking_coffee':['una taza de café','beber café'], 'needs_water':['un vaso de agua','beber agua']},
'fr':{'needs_breakfast':['le petit-déjeuner','mon petit-déjeuner'], 'phrase_frame_drinking_coffee':['une tasse de café','boire du café'], 'needs_water':['un verre d’eau',"un verre d'eau",'boire de l’eau',"boire de l'eau"]},
'de':{'needs_breakfast':['zum Frühstück','mein Frühstück'], 'phrase_frame_drinking_coffee':['eine Tasse Kaffee','Kaffee trinken'], 'needs_water':['ein Glas Wasser','Wasser trinken']},
'it':{'needs_breakfast':['la colazione','per colazione'], 'phrase_frame_drinking_coffee':['una tazza di caffè','bere caffè'], 'needs_water':['un bicchiere di acqua','bere acqua']},
'pt':{'needs_breakfast':['o café da manhã','no café da manhã'], 'phrase_frame_drinking_coffee':['uma xícara de café','beber café'], 'needs_water':['um copo de água','beber água']},
'ar':{'needs_breakfast':['تناول فطور','وجبة فطور'], 'phrase_frame_drinking_coffee':['كوب قهوة','شرب قهوة'], 'needs_water':['كوب ماء','شرب ماء']},
'zh':{'needs_breakfast':['吃早餐','早餐很好吃'], 'phrase_frame_drinking_coffee':['一杯咖啡','咖啡很烫'], 'needs_water':['一杯水','喝水']},
'ja':{'needs_breakfast':['朝食を食べ','朝食がおいしい'], 'phrase_frame_drinking_coffee':['コーヒーをください','温かいコーヒー'], 'needs_water':['水をください','水を一杯']},
'ko':{'needs_breakfast':['아침 식사 시간','아침 식사 준비'], 'phrase_frame_drinking_coffee':['커피 한 잔','따뜻한 커피'], 'needs_water':['물 한 잔','마실 물']},
'sw':{'needs_breakfast':['kwa kifungua kinywa','kifungua kinywa kitamu'], 'phrase_frame_drinking_coffee':['kikombe cha kahawa','kunywa kahawa'], 'needs_water':['glasi ya maji','kunywa maji']},
}
def digest(b):return hashlib.sha256(b).hexdigest()
def u16(s):return len(s.encode('utf-16-le'))//2
proposal=[];evidence=[]
for source,concepts in CONTEXTS.items():
 for target in CONTEXTS:
  if source==target or (source=='en' and target in ['ja','sw']):continue
  manifest=ROOT/f'data/immersion/source-frames-{source}-{target}-catalog.json'
  path=manifest.parent/json.loads(manifest.read_text())['file'];blob=path.read_bytes();pack=json.loads(blob)
  for concept,contexts in concepts.items():
   matches=[p for p in pack['patterns'] if p['id']==f'{source}-{target}:{concept}']
   assert len(matches)==1,(source,target,concept)
   old=matches[0]; variants=[]
   for context in contexts:
    assert context.count(old['source'])==1,(source,concept,context,old['source'])
    at=context.index(old['source']);start=u16(context[:at])
    # Omit contexts already permitted by an identical-face accepted pattern.
    if any(q['source']==old['source'] and q['target']==old['target'] and any(v.get('context_scope') != 'whole_sentence' and not v.get('right_boundary') and v['context'] in context and u16(context[:context.index(v['context'])]) + v['focus_utf16'][0] == start for v in q['variants']) for q in pack['patterns']):
     continue
    variants.append(dict(context=context,context_scope='local_phrase',focus_utf16=[start,start+u16(old['source'])]))
   if not variants:continue
   new=copy.deepcopy(old);new['id']='everyday-noun-008:'+old['id'];new['variants']=variants
   proposal.append(new)
   evidence.append(dict(pattern_id=new['id'],base_pattern_id=old['id'],base_file=path.name,base_sha256=digest(blob),meaning=old['meaning'],original_records=old['original_records'],target_unchanged=True,reading_unchanged=True,permission_evidence='New explicitly authored noun construction; candidate, not independently validated.'))
output=dict(schema='vipi-private-context-proposal-1',active=False,patterns=proposal)
(HERE/'candidate-patterns.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
(HERE/'evidence.json').write_text(json.dumps(dict(scope='Accepted directional senses/targets/readings retained verbatim; new context permissions are authored hypotheses pending native and linguistic review.',records=evidence),ensure_ascii=False,indent=2)+'\n')
print(len(proposal),'patterns',sum(len(p['variants']) for p in proposal),'contexts',len({p['pair'] for p in proposal}),'directions; no active assets written')
