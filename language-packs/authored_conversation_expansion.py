#!/usr/bin/env python3
"""A second bounded everyday batch: places, belongings, travel and meals.

Development authoring only. This does not approve or generalize these examples.
"""
import argparse
import json
from pathlib import Path
from authored_conversation import records, protocol
from build_wiktextract import canonical

DATA={
'phone_device':('a telephone device that is ringing, not an individual speech sound',
'The [phone] is ringing.|El [teléfono] está sonando.|Le [téléphone] sonne.|Das [Telefon] klingelt.|Il [telefono] sta squillando.|O [telefone] está tocando.|ال[هاتف~hātif] يرن.|[电话~diànhuà]响了。|[電話~denwa]が鳴っています。|[전화~jeonhwa]가 울리고 있어요.'),
'friend_person':('a friend as a person, with the possessor outside the lexical focus',
'My [friend] is here.|Mi [amigo] está aquí.|Mon [ami] est ici.|Ein [Freund] von mir ist hier.|Il mio [amico] è qui.|Meu [amigo] está aqui.|[صديق~ṣadīq]ي هنا.|我的[朋友~péngyou]在这里。|私の[友達~tomodachi]はここにいます。|제 [친구~chingu]가 여기 있어요.'),
'house_building':('a residential house with a garden, not a business or a legislature',
'The [house] has a garden.|La [casa] tiene un jardín.|La [maison] a un jardin.|Das [Haus] hat einen Garten.|La [casa] ha un giardino.|A [casa] tem um jardim.|لل[بيت~bayt] حديقة.|这座[房子~fángzi]有一个花园。|その[家~ie]には庭があります。|그 [집~jip]에는 정원이 있어요.'),
'school_place':('a school as an educational place near a park',
'The [school] is near the park.|La [escuela] está cerca del parque.|L’[école] est près du parc.|Die [Schule] ist in der Nähe des Parks.|La [scuola] è vicino al parco.|A [escola] fica perto do parque.|ال[مدرسة~madrasa] قريبة من الحديقة.|[学校~xuéxiào]在公园附近。|[学校~gakkō]は公園の近くにあります。|[학교~hakgyo]는 공원 근처에 있어요.'),
'office_place':('an office as a place of work, not a public position',
'I’m at the [office].|Estoy en la [oficina].|Je suis au [bureau].|Ich bin im [Büro].|Sono in [ufficio].|Estou no [escritório].|أنا في ال[مكتب~maktab].|我在[办公室~bàngōngshì]。|[事務所~jimusho]にいます。|[사무실~samusil]에 있어요.'),
'meeting_event':('a scheduled meeting or discussion beginning at noon',
'The [meeting] starts at noon.|La [reunión] empieza al mediodía.|La [réunion] commence à midi.|Die [Besprechung] beginnt um zwölf Uhr mittags.|La [riunione] inizia a mezzogiorno.|A [reunião] começa ao meio-dia.|يبدأ ال[اجتماع~ijtimāʿ] عند الظهر.|[会议~huìyì]中午开始。|[会議~kaigi]は正午に始まります。|[회의~hoeui]는 정오에 시작해요.'),
'bus_vehicle':('a road passenger bus that is late, not a computer bus',
'The [bus] is late.|El [autobús] llega tarde.|Le [bus] est en retard.|Der [Bus] hat Verspätung.|L’[autobus] è in ritardo.|O [ônibus] está atrasado.|ال[حافلة~ḥāfila] متأخرة.|[公交车~gōngjiāochē]晚点了。|[バス~basu]が遅れています。|[버스~beoseu]가 늦어요.'),
'train_vehicle':('a railway train that is late, not the verb train',
'The [train] is late.|El [tren] llega tarde.|Le [train] est en retard.|Der [Zug] hat Verspätung.|Il [treno] è in ritardo.|O [trem] está atrasado.|ال[قطار~qiṭār] متأخر.|[火车~huǒchē]晚点了。|[列車~ressha]が遅れています。|[기차~gicha]가 늦어요.'),
'ticket_rail':('a purchased train ticket, not a traffic fine or a support request',
'I bought a train [ticket].|Compré un [billete] de tren.|J’ai acheté un [billet] de train.|Ich habe eine [Fahrkarte] für den Zug gekauft.|Ho comprato un [biglietto] del treno.|Comprei uma [passagem] de trem.|اشتريت [تذكرة~tadhkira] قطار.|我买了一张火车[票~piào]。|電車の[切符~kippu]を買いました。|기차[표~pyo]를 샀어요.'),
'airport_place':('an airport as the destination of a journey',
'We’re going to the [airport].|Vamos al [aeropuerto].|Nous allons à l’[aéroport].|Wir fahren zum [Flughafen].|Andiamo all’[aeroporto].|Estamos indo para o [aeroporto].|نحن ذاهبون إلى ال[مطار~maṭār].|我们要去[机场~jīchǎng]。|[空港~kūkō]に行きます。|[공항~gonghang]에 가고 있어요.'),
'hotel_place':('a hotel as paid accommodation near an airport',
'The [hotel] is near the airport.|El [hotel] está cerca del aeropuerto.|L’[hôtel] est près de l’aéroport.|Das [Hotel] ist in der Nähe des Flughafens.|L’[albergo] è vicino all’aeroporto.|O [hotel] fica perto do aeroporto.|ال[فندق~funduq] قريب من المطار.|[酒店~jiǔdiàn]在机场附近。|[ホテル~hoteru]は空港の近くにあります。|[호텔~hotel]은 공항 근처에 있어요.'),
'room_interior':('a quiet hotel room, not available capacity or an arbitrary kind of room',
'The hotel [room] is quiet.|La [habitación] del hotel está tranquila.|La [chambre] d’hôtel est calme.|Das [Zimmer] im Hotel ist ruhig.|La [stanza] dell’albergo è tranquilla.|O [quarto] do hotel está tranquilo.|[غرفة~ghurfa] الفندق هادئة.|酒店的[房间~fángjiān]很安静。|ホテルの[部屋~heya]は静かです。|호텔 [방~bang]이 조용해요.'),
'door_physical':('a physical door being closed, not a metaphorical opportunity',
'Please close the [door].|Por favor, cierra la [puerta].|Ferme la [porte], s’il te plaît.|Bitte schließ die [Tür].|Per favore, chiudi la [porta].|Por favor, feche a [porta].|أغلق ال[باب~bāb] من فضلك.|请关[门~mén]。|[ドア~doa]を閉めてください。|[문~mun]을 닫아 주세요.'),
'key_door':('a physical key for a door, not an answer or musical key',
'Where is the [key] to the door?|¿Dónde está la [llave] de la puerta?|Où est la [clé] de la porte ?|Wo ist der [Schlüssel] für die Tür?|Dov’è la [chiave] della porta?|Onde está a [chave] da porta?|أين [مفتاح~miftāḥ] الباب؟|门的[钥匙~yàoshi]在哪里？|ドアの[鍵~kagi]はどこですか。|문 [열쇠~yeolsoe]가 어디예요?'),
'bag_container':('a bag placed on a table, not a verb or insult',
'The [bag] is on the table.|La [bolsa] está en la mesa.|Le [sac] est sur la table.|Die [Tasche] liegt auf dem Tisch.|La [borsa] è sul tavolo.|A [bolsa] está na mesa.|ال[حقيبة~ḥaqība] على الطاولة.|[包~bāo]在桌子上。|[かばん~kaban]はテーブルの上にあります。|[가방~gabang]이 탁자 위에 있어요.'),
'breakfast_meal':('breakfast as a prepared morning meal',
'[Breakfast] is ready.|El [desayuno] está listo.|Le [petit-déjeuner] est prêt.|Das [Frühstück] ist fertig.|La [colazione] è pronta.|O [café da manhã] está pronto.|ال[فطور~fuṭūr] جاهز.|[早餐~zǎocān]准备好了。|[朝食~chōshoku]ができました。|[아침 식사~achim siksa]가 준비됐어요.'),
'lunch_meal':('lunch as a prepared midday meal',
'[Lunch] is ready.|El [almuerzo] está listo.|Le [déjeuner] est prêt.|Das [Mittagessen] ist fertig.|Il [pranzo] è pronto.|O [almoço] está pronto.|ال[غداء~ghadāʾ] جاهز.|[午饭~wǔfàn]准备好了。|[昼食~chūshoku]ができました。|[점심~jeomsim]이 준비됐어요.'),
'dinner_meal':('dinner as a prepared evening meal',
'[Dinner] is ready.|La [cena] está lista.|Le [dîner] est prêt.|Das [Abendessen] ist fertig.|La [cena] è pronta.|O [jantar] está pronto.|ال[عشاء~ʿashāʾ] جاهز.|[晚饭~wǎnfàn]准备好了。|[夕食~yūshoku]ができました。|[저녁 식사~jeonyeok siksa]가 준비됐어요.'),
'weather_conditions':('pleasant outdoor weather, not a verb',
'The [weather] is nice.|Hace buen [tiempo].|Il fait beau [temps].|Das [Wetter] ist schön.|Il [tempo] è bello.|O [tempo] está bom.|ال[طقس~ṭaqs] جميل.|[天气~tiānqì]很好。|[天気~tenki]がいいです。|[날씨~nalssi]가 좋아요.'),
'rain_weather':('rainfall that has stopped',
'The [rain] has stopped.|La [lluvia] ha parado.|La [pluie] s’est arrêtée.|Der [Regen] hat aufgehört.|La [pioggia] è finita.|A [chuva] parou.|توقف ال[مطر~maṭar].|[雨~yǔ]停了。|[雨~ame]がやみました。|[비~bi]가 그쳤어요.'),
}


def expanded_records():
    for record in records(DATA):
        record['provenance']['priority_basis']='UD training and NUS SMS development frequency priorities: everyday places, travel, belongings and meals; authored examples'
        yield record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);values=list(expanded_records())
    with (a.output/'records.jsonl').open('x') as stream:
        for value in values:stream.write(canonical(value)+'\n')
    probe=protocol(values);probe['qa_run_id']='004';probe['scope']='Second everyday development batch; no reserved SMS sentences used'
    (a.output/'phrase-protocol.json').write_text(json.dumps(probe,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'records':len(values),'concepts':len(DATA),'pairs':90,'linguistic_acceptance':False}))
