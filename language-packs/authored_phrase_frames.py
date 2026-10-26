#!/usr/bin/env python3
"""Small explicit phrase-scope development set; never independent acceptance.

Brackets delimit lexical focus. Each frame is a literal construction whose
surroundings were assessed here, independently of earlier exact-sentence scopes.
No automatic promotion of dictionary senses or corpus translations occurs.
"""
import argparse
import json
from pathlib import Path
from authored_everyday import mapping
from authored_conversation import LANGUAGES, protocol
from build_wiktextract import canonical, digest_file, readable_roman
from mapping_catalog import validate

# (meaning, ten sentence templates, ten bounded constructions)
DATA={
'reading_book':(
 'a book being read as textual material, not making a reservation or an account ledger operation',
 ['I am {f} now.','Estoy {f} ahora.','Je {f} maintenant.','Ich {f} gerade.','Sto {f} adesso.',
  'Estou {f} agora.','أنا {f} الآن.','我正在{f}。','今、{f}。','지금 {f}.'],
 ['reading a [book]','leyendo un [libro]','lis un [livre]','lese ein [Buch]','leggendo un [libro]',
  'lendo um [livro]','أقرأ [كتاب~kitāb]ًا','读一本[书~shū]','[本~hon]を読んでいます','[책~chaek]을 읽고 있어요']),
'drinking_water':(
 'water consumed as a beverage, not watering plants, a geographic body, or a figurative expression',
 ['I am {f} now.','Estoy {f} ahora.','Je {f} maintenant.','Ich {f} gerade.','Sto {f} adesso.',
  'Estou {f} agora.','أنا {f} الآن.','我正在{f}。','今、{f}。','지금 {f}.'],
 ['drinking [water]','bebiendo [agua]','bois de l’[eau]','trinke [Wasser]','bevendo [acqua]',
  'bebendo [água]','أشرب ال[ماء~mā’]','喝[水~shuǐ]','[水~mizu]を飲んでいます','[물~mul]을 마시고 있어요']),
'birthday_party':(
 'a party celebrating a birthday, not a political organization or a legal party',
 ['The {f} is tomorrow.','La {f} es mañana.','La {f} est demain.','Die {f} ist morgen.',
  'La {f} è domani.','A {f} é amanhã.','{f} غدًا.','{f}在明天。','{f}は明日です。','{f} 내일이에요.'],
 ['birthday [party]','[fiesta] de cumpleaños','[fête] d’anniversaire','[Feier] zum Geburtstag',
  '[festa] di compleanno','[festa] de aniversário','[حفل~ḥafl] عيد الميلاد','生日[派对~pàiduì]',
  '誕生日[パーティー~pātī]','생일 [파티~pati]는']),
'phone_charger':(
 'a device that charges a telephone battery, not a horse, serving plate, or person charging forward',
 ['Where is the {f}?','¿Dónde está el {f}?','Où est le {f} ?','Wo ist das {f}?',
  'Dov’è il {f}?','Onde está o {f}?','أين {f}؟','{f}在哪里？','{f}はどこですか。','{f} 어디예요?'],
 ['phone [charger]','[cargador] del teléfono','[chargeur] du téléphone','[Ladegerät] fürs Telefon',
  '[caricabatterie] del telefono','[carregador] do telefone','[شاحن~shāḥin] الهاتف','手机[充电器~chōngdiànqì]',
  '携帯の[充電器~jūdenki]','휴대폰 [충전기~chungjeongi]가']),
}


def parse(marked):
    a=marked.index('[');b=marked.index(']');focus,*reading=marked[a+1:b].split('~')
    return marked[:a]+focus+marked[b+1:],focus,readable_roman(reading[0]) if reading else ''


def pattern(concept,language,focus):
    L=lambda text:{'literal':text}
    S=lambda choices:{'slot':choices}
    F={'focus':focus}
    # Explicit alternatives retain the same lexical meaning. They are authored
    # spellings, never inferred stems or unrestricted wildcards.
    if concept=='reading_book':
        return {
            'en':[L('read'),S(['ing a ',' a ','s a ']),F],
            'es':[S(['leyendo','leo','lees','lee','leemos','leen','leer']),L(' un '),F],
            'fr':[S(['lis','lit','lisons','lisez','lisent','lire']),L(' un '),F],
            'de':[S(['lese','lese jetzt','liest','liest jetzt','lesen','lesen jetzt','lest','lest jetzt']),L(' ein '),F],
            'it':[S(['leggendo','leggo','leggi','legge','leggiamo','leggono','leggere']),L(' un '),F],
            'pt':[S(['lendo','leio','lê','lemos','leem','ler']),L(' um '),F],
            'ja':[F,L('を'),S(['読んでいます','読んでいる','読んでる','読みます','読む','読んでいた'])],
            'ko':[F,L('을 '),S(['읽고 있어요','읽고있다','읽고 있다','읽어요','읽습니다'])],
        }.get(language)
    if concept=='drinking_water':
        return {
            'en':[L('drink'),S(['ing ',' ','s ']),F],
            'es':[L('beb'),S(['iendo ','o ','es ','e ','emos ','en ','er ']),F],
            'fr':[L('bo'),S(['is','it','ire']),L(' de l'),S(['’',"'"]),F],
            'de':[L('trink'),S(['e ','e jetzt ','t ','t jetzt ','en ','en jetzt ']),F],
            'it':[L('bev'),S(['endo ','o ','i ','e ','iamo ','ono ','ere ']),F],
            'pt':[L('beb'),S(['endo ','o ','e ','emos ','em ','er ']),F],
            'ja':[F,L('を'),S(['飲んでいます','飲んでいる','飲んでる','飲みます','飲む','飲んでいた'])],
            'ko':[F,L('을 '),S(['마시고 있어요','마시고있다','마시고 있다','마셔요','마십니다'])],
        }.get(language)
    if concept=='birthday_party':
        return {'fr':[F,L(' d'),S(['’',"'"]),L('anniversaire')],
                'ko':[L('생일 '),F,S(['는','가','에','를','의'])]}.get(language)
    if concept=='phone_charger':
        return {'fr':[F,L(' '),S(['du','de']),L(' téléphone')],
                'pt':[F,L(' '),S(['do','de']),L(' telefone')],
                'ko':[L('휴대폰 '),F,S(['가','는','를','에','의'])]}.get(language)
    return None


def records():
    for concept,(meaning,templates,frames) in DATA.items():
        forms={}
        for language,template,marked in zip(LANGUAGES,templates,frames,strict=True):
            frame,focus,reading=parse(marked)
            forms[language]=(template.format(f=frame),frame,focus,reading)
        for source,(original,left_frame,left,_) in forms.items():
            for target,(translation,right_frame,right,reading) in forms.items():
                if source==target:continue
                row=mapping('phrase_frame_'+concept,source,target,left,right,original,translation,meaning,reading)
                row['usage'].update(context_extent='local_phrase',context_generalization='explicit literal phrase in a larger message',
                    source_frame_span=[original.index(left_frame),original.index(left_frame)+len(left_frame)],
                    target_frame_span=[translation.index(right_frame),translation.index(right_frame)+len(right_frame)],
                    permitted_context='Literal '+meaning+'. Subject, tense, negation, ownership and clause embedding outside the focus remain unchanged.',
                    abstain_when=['A matching source or target construction is absent.',
                        'The matched focus or corresponding target construction repeats ambiguously.',
                        'Another matching record assigns a conflicting meaning.',
                        'The focus overlaps protected text or lacks a required readable transliteration.'])
                row['provenance']['priority_basis']='Common reading, drinking, social-event and device constructions; authored without reserved corpus messages'
                for side,language,word in [('source',source,left),('target',target,right)]:
                    parts=pattern(concept,language,word)
                    if parts is not None:row['usage'][side+'_frame_pattern']=parts
                validate(row);yield row


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);rows=list(records())
    (a.output/'records.jsonl').write_text(''.join(canonical(r)+'\n' for r in rows))
    probe=protocol(rows);probe['qa_run_id']='007';probe['scope']='Authored phrase-frame development, not held-out acceptance'
    (a.output/'phrase-protocol.json').write_text(json.dumps(probe,ensure_ascii=False,indent=2)+'\n')
    fixture={'schema':'vipi-reviewed-frame-fixture-1','synthetic_contexts':True,'linguistic_acceptance':False,
        'records_sha256':digest_file(a.output/'records.jsonl'),'rows':rows}
    (a.output/'native-fixture.json').write_text(canonical(fixture)+'\n')
    print(canonical({'records':len(rows),'concepts':len(DATA),'pairs':90,'release_ready':False}))
