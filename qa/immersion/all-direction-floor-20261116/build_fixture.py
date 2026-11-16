"""Finite authored chat probe, not training data or a population estimate."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
# Authored after inspecting existing concept names; sentences are not copied from packs.
# No translation provider, pivot, dictionary generation, or runtime permissions.
MESSAGES={
'en':['Please bring some water when you come upstairs.','I left my book on the kitchen table.','The music is too loud; could you turn it down?'],
'es':['Por favor, trae agua cuando subas.','Dejé mi libro en la mesa de la cocina.','La música está demasiado alta, ¿puedes bajarla?'],
'fr':["Apporte de l’eau quand tu montes, s’il te plaît.","J’ai laissé mon livre sur la table de la cuisine.","La musique est trop forte, tu peux baisser le son ?"],
'de':['Bring bitte etwas Wasser mit, wenn du hochkommst.','Ich habe mein Buch auf dem Küchentisch liegen lassen.','Die Musik ist zu laut, kannst du sie leiser machen?'],
'it':["Porta un po’ d’acqua quando sali, per favore.",'Ho lasciato il mio libro sul tavolo della cucina.','La musica è troppo alta, puoi abbassarla?'],
'pt':['Traz água quando subires, por favor.','Deixei o meu livro na mesa da cozinha.','A música está muito alta, podes baixar o volume?'],
'ar':['أحضر بعض الماء عندما تصعد، من فضلك.','تركت كتابي على طاولة المطبخ.','الموسيقى عالية جدا، هل يمكنك خفض الصوت؟'],
'zh':['你上楼的时候请带点水。','我把书忘在厨房的桌子上了。','音乐太响了，可以调小一点吗？'],
'ja':['上に来るとき、水を持ってきてください。','台所のテーブルに本を置き忘れました。','音楽がうるさいので、音量を下げてもらえますか。'],
'ko':['올라올 때 물 좀 가져다주세요.','부엌 식탁에 책을 두고 왔어요.','음악이 너무 시끄러운데 소리를 줄여 줄래요?'],
'sw':['Tafadhali leta maji ukipanda juu.','Niliacha kitabu changu juu ya meza jikoni.','Muziki una sauti kubwa sana, unaweza kupunguza sauti?'],
}
rows=[]
for source,texts in MESSAGES.items():
 for target in MESSAGES:
  if source==target:continue
  for concept,text in zip(['water','book','music'],texts):
   rows.append(dict(id=f'{source}-{target}:{concept}',source_language=source,target_language=target,original=text,opportunity_concept=concept,expectation='Observe useful single-word output or explicit abstention; do not force unsafe mapping.'))
assets={}
for source in MESSAGES:
 for target in MESSAGES:
  if source==target:continue
  name=f'source-frames-{source}-{target}-catalog.json'
  manifest=ROOT/'data/immersion'/name
  for p in [manifest,manifest.parent/json.loads(manifest.read_text())['file']]:
   b=p.read_bytes();assets[p.name]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
fixture={'schema':1,'languages':list(MESSAGES),'directions':110,'cases':rows,'controls':[],'assets':assets,'scope':'330 authored observations in 110 directions; sentences frozen before runtime capture. Concept selection informed by existing packs; not blind, human conversation, or population coverage. Three concepts alone cannot establish release quality.','automatic_density':0.25,'direct_density':0.5,'requirements':['Use actual bundled default without injected lookup.','Run automatic source detection and direct configured-pair lookup separately.','Capture source detection, abstention reason, emitted source/target/reading, concept/output ID, and translation/readiness call counts.','Every emitted non-Latin target needs a usable Latin reading; Latin targets may use their original Latin spelling.','For each target language, synthesize one actually emitted word with selected engine/voice/locale and output duration; eligibility alone is not acoustic validation.','Retain same-script and non-Roman source detection abstentions rather than overriding them silently.']}
p=Path(__file__).with_name('fixtures.json');p.write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
print(p, len(rows))
