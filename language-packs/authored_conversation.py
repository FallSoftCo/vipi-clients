#!/usr/bin/env python3
"""Corpus-prioritized development contexts, with explicit lexical boundaries.

Each line contains ten authored sentence references. A bracket marks the lexical
focus, and ~ separates a readable Latin transliteration. No target article,
possessor, case particle, or surrounding grammar is copied into the replacement.
These authored references are not an independent acceptance set.
"""
import argparse
import json
from pathlib import Path
from authored_everyday import mapping
from build_wiktextract import canonical, readable_roman
from mapping_catalog import validate

LANGUAGES=('en','es','fr','de','it','pt','ar','zh','ja','ko')
DATA={
'time_duration':('time available to complete an activity, not clock time or an occasion',
 'I need more [time].|Necesito más [tiempo].|J’ai besoin de plus de [temps].|Ich brauche mehr [Zeit].|Ho bisogno di più [tempo].|Preciso de mais [tempo].|أحتاج إلى مزيد من [الوقت~al-waqt].|我需要更多[时间~shíjiān]。|もっと[時間~jikan]が必要です。|[시간~sigan]이 더 필요해요.'),
'today':('on this present calendar day',
 'I’m working [today].|Trabajo [hoy].|Je travaille [aujourd’hui].|Ich arbeite [heute].|Lavoro [oggi].|Trabalho [hoje].|أعمل [اليوم~al-yawm].|我[今天~jīntiān]上班。|[今日~kyō]は仕事です。|[오늘~oneul]은 일해요.'),
'tomorrow':('on the calendar day after today, not the morning',
 'I’m working [tomorrow].|Trabajo [mañana].|Je travaille [demain].|Ich arbeite [morgen].|Lavoro [domani].|Trabalho [amanhã].|أعمل [غدًا~ghadan].|我[明天~míngtiān]上班。|[明日~ashita]は仕事です。|[내일~naeil]은 일해요.'),
'yesterday':('on the calendar day before today',
 'I worked [yesterday].|Trabajé [ayer].|J’ai travaillé [hier].|Ich habe [gestern] gearbeitet.|Ho lavorato [ieri].|Trabalhei [ontem].|عملت [أمس~ams].|我[昨天~zuótiān]上班了。|[昨日~kinō]は仕事でした。|[어제~eoje]는 일했어요.'),
'week':('a calendar week, with next outside the focus',
 'See you next [week].|Nos vemos la próxima [semana].|On se voit la [semaine] prochaine.|Wir sehen uns nächste [Woche].|Ci vediamo la prossima [settimana].|Até a próxima [semana].|نراك في [الأسبوع~al-usbūʿ] القادم.|下[周~zhōu]见。|来[週~shū]会いましょう。|다음 [주~ju]에 만나요.'),
'month':('a calendar month, with next outside the focus',
 'I’m moving next [month].|Me mudo el próximo [mes].|Je déménage le [mois] prochain.|Ich ziehe nächsten [Monat] um.|Trasloco il prossimo [mese].|Vou me mudar no próximo [mês].|سأنتقل في [الشهر~ash-shahr] القادم.|我下个[月~yuè]搬家。|来[月~getsu]引っ越します。|다음 [달~dal]에 이사해요.'),
'year':('a calendar year, with last outside the focus',
 'We moved here last [year].|Nos mudamos aquí el [año] pasado.|Nous avons emménagé ici l’[année] dernière.|Wir sind letztes [Jahr] hierhergezogen.|Ci siamo trasferiti qui l’[anno] scorso.|Nós nos mudamos para cá no [ano] passado.|انتقلنا إلى هنا [العام~al-ʿām] الماضي.|我们去[年~nián]搬到了这里。|去[年~nen]ここに引っ越しました。|우리는 작[년~nyeon]에 여기로 이사했어요.'),
'question':('a request for information, not a doubt about legitimacy',
 'I have a [question].|Tengo una [pregunta].|J’ai une [question].|Ich habe eine [Frage].|Ho una [domanda].|Tenho uma [pergunta].|لدي [سؤال~suʾāl].|我有一个[问题~wèntí]。|[質問~shitsumon]があります。|[질문~jilmun]이 있어요.'),
'problem':('a difficulty that needs resolving, not a question requesting information',
 'There is a [problem].|Hay un [problema].|Il y a un [problème].|Es gibt ein [Problem].|C’è un [problema].|Há um [problema].|هناك [مشكلة~mushkila].|有一个[问题~wèntí]。|[問題~mondai]があります。|[문제~munje]가 있어요.'),
'food':('food to eat, not an idiom or an abstract source of thought',
 'We need more [food].|Necesitamos más [comida].|Il nous faut plus de [nourriture].|Wir brauchen mehr [Essen].|Abbiamo bisogno di più [cibo].|Precisamos de mais [comida].|نحتاج إلى مزيد من [الطعام~aṭ-ṭaʿām].|我们需要更多[食物~shíwù]。|もっと[食べ物~tabemono]が必要です。|[음식~eumsik]이 더 필요해요.'),
'price':('the amount charged for a purchase',
 'The [price] is too high.|El [precio] es demasiado alto.|Le [prix] est trop élevé.|Der [Preis] ist zu hoch.|Il [prezzo] è troppo alto.|O [preço] é alto demais.|[السعر~as-siʿr] مرتفع جدًا.|[价格~jiàgé]太高了。|[値段~nedan]が高すぎます。|[가격~gagyeok]이 너무 높아요.'),
'family':('one’s family as a group of people, not a biological classification',
 'My [family] lives nearby.|Mi [familia] vive cerca.|Ma [famille] habite à proximité.|Meine [Familie] wohnt in der Nähe.|La mia [famiglia] abita qui vicino.|Minha [família] mora perto.|تعيش [عائلتي~ʿāʾilatī] بالقرب من هنا.|我的[家人~jiārén]住在附近。|私の[家族~kazoku]は近くに住んでいます。|제 [가족~gajok]은 근처에 살아요.'),
'car':('a car used for transport, not a railway carriage',
 'The [car] is outside.|El [coche] está fuera.|La [voiture] est dehors.|Das [Auto] steht draußen.|La [macchina] è fuori.|O [carro] está lá fora.|[السيارة~as-sayyāra] في الخارج.|[汽车~qìchē]在外面。|[車~kuruma]は外にあります。|[자동차~jadongcha]는 밖에 있어요.'),
'book_reading':('a book as reading material, not the reservation verb',
 'I’m reading a [book].|Estoy leyendo un [libro].|Je lis un [livre].|Ich lese ein [Buch].|Sto leggendo un [libro].|Estou lendo um [livro].|أقرأ [كتاب~kitāb]ًا.|我在读一本[书~shū]。|[本~hon]を読んでいます。|[책~chaek]을 읽고 있어요.'),
'message':('a written chat message, not an implied moral or meaning',
 'I sent a [message].|Envié un [mensaje].|J’ai envoyé un [message].|Ich habe eine [Nachricht] geschickt.|Ho inviato un [messaggio].|Enviei uma [mensagem].|أرسلت [رسالة~risāla].|我发了一条[消息~xiāoxi]。|[メッセージ~messēji]を送りました。|[메시지~mesiji]를 보냈어요.'),
'address':('a physical destination address, not a speech or email address',
 'What is the hotel’s [address]?|¿Cuál es la [dirección] del hotel?|Quelle est l’[adresse] de l’hôtel ?|Wie lautet die [Adresse] des Hotels?|Qual è l’[indirizzo] dell’albergo?|Qual é o [endereço] do hotel?|ما [عنوان~ʿunwān] الفندق؟|酒店的[地址~dìzhǐ]是什么？|ホテルの[住所~jūsho]は何ですか。|호텔 [주소~juso]가 뭐예요?'),
'station_rail':('a railway station, not a police station or a broadcast station',
 'Where is the train [station]?|¿Dónde está la [estación] de tren?|Où est la [gare] ?|Wo ist der [Bahnhof]?|Dov’è la [stazione] ferroviaria?|Onde fica a [estação] de trem?|أين [محطة~maḥaṭṭa] القطار؟|火车[站~zhàn]在哪里？|[駅~eki]はどこですか。|기차[역~yeok]이 어디예요?'),
'money':('money available to spend, not a monetary value or a specific currency',
 'I don’t have enough [money].|No tengo suficiente [dinero].|Je n’ai pas assez d’[argent].|Ich habe nicht genug [Geld].|Non ho abbastanza [soldi].|Não tenho [dinheiro] suficiente.|ليس لدي ما يكفي من [المال~al-māl].|我的[钱~qián]不够。|[お金~okane]が足りません。|[돈~don]이 부족해요.'),
'help_noun':('assistance requested as a noun, not the verb help',
 'I need [help].|Necesito [ayuda].|J’ai besoin d’[aide].|Ich brauche [Hilfe].|Ho bisogno di [aiuto].|Preciso de [ajuda].|أحتاج إلى [مساعدة~musāʿada].|我需要[帮助~bāngzhù]。|[助け~tasuke]が必要です。|[도움~doum]이 필요해요.'),
'work_job':('a paid job or employment sought, not physical work or an artistic work',
 'I’m looking for a [job].|Busco un [trabajo].|Je cherche un [emploi].|Ich suche einen [Job].|Cerco un [lavoro].|Estou procurando um [emprego].|أبحث عن [وظيفة~waẓīfa].|我在找[工作~gōngzuò]。|[仕事~shigoto]を探しています。|[일자리~iljari]를 찾고 있어요.'),
}


def marked(value):
    if value.count('[')!=1 or value.count(']')!=1: raise ValueError('One explicit focus required')
    before,rest=value.split('[',1); focus,after=rest.split(']',1)
    parts=focus.split('~');word=parts[0];reading=parts[1] if len(parts)==2 else ''
    return before+word+after,word,readable_roman(reading) if reading else ''


ARABIC_ARTICLES={
    'time_duration':('وقت','waqt'),'today':None,'week':('أسبوع','usbūʿ'),
    'month':('شهر','shahr'),'year':('عام','ʿām'),'food':('طعام','ṭaʿām'),
    'price':('سعر','siʿr'),'car':('سيارة','sayyāra'),'money':('مال','māl')}


def records():
    for identity,(meaning,line) in DATA.items():
        columns=line.split('|')
        if len(columns)!=10: raise ValueError('All ten languages required')
        entries=dict(zip(LANGUAGES,map(marked,columns)))
        # Arabic al- belongs to the sentence grammar. "Today" is a
        # lexicalized adverb and retains its conventional surface al-yawm.
        article=ARABIC_ARTICLES.get(identity)
        if article:
            sentence,old,_=entries['ar'];word,reading=article
            if old!='ال'+word: raise ValueError('Unexpected definite Arabic form')
            entries['ar']=(sentence,word,readable_roman(reading))
        for source,(original,left,_) in entries.items():
            for target,(translation,right,reading) in entries.items():
                if source==target:continue
                record=mapping('conversation_'+identity,source,target,left,right,original,translation,meaning,reading)
                record['provenance']['priority_basis']='UD 2.18 English-EWT/French-Rhapsodie training frequency audit; authored expansion'
                # Lexicalized time words retain their conventional form, but
                # attached possessors must never be taught as an unowned noun.
                if identity=='family' and (source=='ar' or target=='ar'): continue
                record['usage']['context_generalization']='exact authored sentence only'
                validate(record);yield record


def protocol(values):
    samples=[]
    for record in values:
        text=record['source_context'];start,end=record['source_span']
        samples.append({'source':record['source_language'],'target':record['target_language'],
            'original':text,'source_word':record['source'],'start':len(text[:start].encode('utf-16-le'))//2,
            'end':len(text[:end].encode('utf-16-le'))//2,'expected_target':record['target'],
            'expected_reading':record['reading'],'case':record['logical_id'],'concept':record['meaning'],
            'evaluation_scope':'corpus-prioritized authored development; not held out'})
    return {'schema':'vipi-local-phrase-probe-1','scope':'Expanded authored conversation contexts','qa_run_id':'002',
        'window_extents':[[0,0],[1,0],[0,1],[1,1],[2,0],[0,2],[2,2]],
        'maximum_phrase_characters':192,'maximum_window_words':8,'meaning_acceptance':False,'samples':samples}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False);values=list(records())
    with (args.output/'records.jsonl').open('x') as stream:
        for value in values:stream.write(canonical(value)+'\n')
    (args.output/'phrase-protocol.json').write_text(json.dumps(protocol(values),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'records':len(values),'concepts':len(DATA),'pairs':90,'linguistic_acceptance':False}))
