"""Freeze bounded, authored feasibility cases; human review required."""
import json,hashlib
from pathlib import Path
rows=[
('en','es','The train leaves from platform three in ten minutes.','train','noun: railway vehicle'),
('en','es','I train new volunteers every Saturday morning.','train','verb: teach or prepare people'),
('en','fr','She went to the bank to deposit her paycheck.','bank','financial institution'),
('en','fr','We sat on the bank and watched the river flow.','bank','land beside a river, not financial institution'),
('en','de','I am feeling under the weather, so I will stay home.','under the weather','idiom: feeling ill; literal weather wording is misleading'),
('en','ja','Sounds good, see you after lunch!','Sounds good','short informal acceptance, not a sound recording'),
('es','en','La llave está junto a la taza azul.','llave','key for a lock; do not infer an English sense from string alone'),
('fr','en','On se retrouve devant la bibliothèque après le cours ?','bibliothèque','library as a place; not a bookcase in this context'),
('de','en','Ich habe meinen Termin auf Freitag verschoben.','Termin','appointment, not an academic term'),
('it','en','Puoi spegnere la luce prima di uscire?','luce','light, referring to the lamp or lighting'),
('pt','en','O ônibus já saiu; vamos esperar o próximo.','ônibus','bus as passenger vehicle'),
('ar','en','هل يمكنك إغلاق النافذة قبل أن نخرج؟','النافذة','the window; full definite noun carrier'),
('zh','en','明天下午我们在图书馆门口见面吧。','图书馆','library building, not a bookstore'),
('ja','en','駅の前で友達を十分待ちました。','駅','railway station; friend marker is separate'),
('ko','en','회의가 끝나면 저에게 메시지를 보내 주세요.','회의','meeting; Korean particle 가 follows focus'),
('sw','en','Tafadhali funga dirisha kabla mvua haijaanza.','dirisha','window; not the rain'),
('sw','en','Sawa, nitakuona kesho asubuhi.','kesho','tomorrow, not morning'),
('en','ar','Could you put the red cup beside the sink?','cup','drinking vessel; Arabic target needs Latin reading'),
]
def u16(s):return len(s.encode('utf-16-le'))//2
cases=[]
for i,(source,target,text,focus,sense) in enumerate(rows,1):
 assert text.count(focus)==1; start=u16(text[:text.index(focus)]);cases.append({'id':f'local-{i:02d}','source_language':source,'target_language':target,'original':text,'focus':focus,'focus_utf16':[start,start+u16(focus)],'meaning_note':sense})
result={'schema':'vipi-local-translation-feasibility-1','purpose':'Compare local full-message translation with source-attributed or phrase-only selection and independently review semantic alignment and Latin readings. Authored cases, not statistical accuracy or provider guarantees. No model downloads; record unavailable models.','cases':cases}
b=(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();p=Path(__file__).with_name('fixtures.json');p.write_bytes(b);print(hashlib.sha256(b).hexdigest())
