#!/usr/bin/env python3
"""Everyday routines selected from development frequency gaps, not test messages.

Explicit lexical focus keeps ownership, negation and surrounding grammar native.
These generated references require content-bound assessment and native execution;
they are never independent evidence of broad conversational accuracy.
"""
import argparse
import json
from pathlib import Path
from authored_conversation import records, protocol
from build_wiktextract import canonical

DATA={
'morning_time':('the morning part of a day, not tomorrow',
'I study in the [morning].|Estudio por la [mañana].|J’étudie le [matin].|Ich lerne am [Morgen].|Studio la [mattina].|Estudo de [manhã].|أدرس في ال[صباح~ṣabāḥ].|我在[早上~zǎoshang]学习。|[朝~asa]に勉強します。|[아침~achim]에 공부해요.'),
'night_time':('the nighttime period, not a greeting',
'I work at [night].|Trabajo de [noche].|Je travaille la [nuit].|Ich arbeite in der [Nacht].|Lavoro di [notte].|Trabalho à [noite].|أعمل في ال[ليل~layl].|我在[夜间~yèjiān]工作。|[夜~yoru]に働いています。|[밤~bam]에 일해요.'),
'weekend_days':('the weekend as a period of days, not a duration of one week',
'I’m free this [weekend].|Estoy libre este [fin de semana].|Je suis libre ce [week-end].|Ich habe dieses [Wochenende] frei.|Sono libero questo [fine settimana].|Estou livre neste [fim de semana].|أنا متفرغ في [نهاية الأسبوع~nihāyat al-usbūʿ] هذه.|这个[周末~zhōumò]我有空。|今[週末~shūmatsu]は暇です。|이번 [주말~jumal]에 시간이 있어요.'),
'class_session':('a scheduled class at school, not a social category',
'The [class] starts soon.|La [clase] empieza pronto.|Le [cours] commence bientôt.|Der [Unterricht] beginnt bald.|La [lezione] inizia presto.|A [aula] começa em breve.|تبدأ ال[حصة~ḥiṣṣa] قريبًا.|[课~kè]快开始了。|[授業~jugyō]がもうすぐ始まります。|[수업~sueop]이 곧 시작해요.'),
'teacher_person':('a teacher who explains a lesson',
'The [teacher] explains the lesson.|El [profesor] explica la lección.|Le [professeur] explique la leçon.|Der [Lehrer] erklärt die Lektion.|L’[insegnante] spiega la lezione.|O [professor] explica a lição.|يشرح ال[معلم~muʿallim] الدرس.|[老师~lǎoshī]在讲课。|[先生~sensei]が授業の内容を説明します。|[선생님~seonsaengnim]이 수업 내용을 설명해요.'),
'student_person':('a university student reading a book',
'The university [student] is reading a book.|El [estudiante] universitario está leyendo un libro.|L’[étudiant] de l’université lit un livre.|Der [Student] an der Universität liest ein Buch.|Lo [studente] universitario sta leggendo un libro.|O [estudante] universitário está lendo um livro.|يقرأ ال[طالب~ṭālib] الجامعي كتابًا.|大学[学生~xuésheng]正在看书。|大学の[学生~gakusei]が本を読んでいます。|대학교 [학생~haksaeng]이 책을 읽고 있어요.'),
'exam_school':('a school examination, not a medical examination',
'The school [exam] is tomorrow.|El [examen] escolar es mañana.|L’[examen] scolaire est demain.|Die [Prüfung] in der Schule ist morgen.|L’[esame] scolastico è domani.|A [prova] da escola é amanhã.|ال[امتحان~imtiḥān] المدرسي غدًا.|学校的[考试~kǎoshì]在明天。|学校の[試験~shiken]は明日です。|학교 [시험~siheom]은 내일이에요.'),
'home_residence':('home as a person’s residence, not a software home page',
'I’m at [home].|Estoy en [casa].|Je suis à la [maison].|Ich bin zu [Hause].|Sono a [casa].|Estou em [casa].|أنا في ال[بيت~bayt].|我在[家~jiā]。|[家~ie]にいます。|[집~jip]에 있어요.'),
'email_message':('one electronic mail message that was sent',
'I sent an [email].|Envié un [correo electrónico].|J’ai envoyé un [courriel].|Ich habe eine [E-Mail] geschickt.|Ho inviato un’[email].|Enviei um [e-mail].|أرسلت [رسالة بريد إلكتروني~risālat barīd iliktrūnī].|我发了一封[电子邮件~diànzǐ yóujiàn]。|[メール~mēru]を送りました。|[이메일~imeil]을 보냈어요.'),
'call_phone':('a telephone call, not a shout or decision',
'The phone [call] was short.|La [llamada] telefónica fue corta.|L’[appel] téléphonique était court.|Das [Telefonat] war kurz.|La [telefonata] è stata breve.|A [ligação] telefônica foi curta.|كانت ال[مكالمة~mukālama] الهاتفية قصيرة.|这次[通话~tōnghuà]很短。|[通話~tsūwa]は短かったです。|[통화~tonghwa]가 짧았어요.'),
'plan_arrangement':('a plan for a trip, not a drawing or subscription',
'What is the [plan] for the trip?|¿Cuál es el [plan] para el viaje?|Quel est le [plan] pour le voyage ?|Was ist der [Plan] für die Reise?|Qual è il [piano] per il viaggio?|Qual é o [plano] para a viagem?|ما [خطة~khuṭṭa] الرحلة؟|旅行的[计划~jìhuà]是什么？|旅行の[計画~keikaku]は何ですか。|여행 [계획~gyehoek]이 뭐예요?'),
'news_information':('news or recently received information',
'I have good [news].|Tengo buenas [noticias].|J’ai de bonnes [nouvelles].|Ich habe gute [Nachrichten].|Ho buone [notizie].|Tenho boas [notícias].|لدي [أخبار~akhbār] جيدة.|我有好[消息~xiāoxi]。|いい[知らせ~shirase]があります。|좋은 [소식~sosik]이 있어요.'),
'movie_film':('a movie watched for entertainment, not a thin coating',
'We watched a [movie].|Vimos una [película].|Nous avons regardé un [film].|Wir haben einen [Film] gesehen.|Abbiamo guardato un [film].|Assistimos a um [filme].|شاهدنا [فيلم~film]ًا.|我们看了一部[电影~diànyǐng]。|[映画~eiga]を見ました。|[영화~yeonghwa]를 봤어요.'),
'music_sound':('music being listened to',
'I’m listening to [music].|Estoy escuchando [música].|J’écoute de la [musique].|Ich höre [Musik].|Sto ascoltando [musica].|Estou ouvindo [música].|أستمع إلى ال[موسيقى~mūsīqā].|我在听[音乐~yīnyuè]。|[音楽~ongaku]を聴いています。|[음악~eumak]을 듣고 있어요.'),
'photo_image':('a photograph taken with a camera',
'I took a [photo].|Tomé una [foto].|J’ai pris une [photo].|Ich habe ein [Foto] gemacht.|Ho scattato una [foto].|Tirei uma [foto].|التقطت [صورة~ṣūra].|我拍了一张[照片~zhàopiàn]。|[写真~shashin]を撮りました。|[사진~sajin]을 찍었어요.'),
'birthday_day':('the anniversary of a person’s birth',
'My [birthday] is tomorrow.|Mi [cumpleaños] es mañana.|Mon [anniversaire] est demain.|Mein [Geburtstag] ist morgen.|Il mio [compleanno] è domani.|Meu [aniversário] é amanhã.|[عيد ميلاد~ʿīd mīlād]ي غدًا.|明天是我的[生日~shēngrì]。|明日は私の[誕生日~tanjōbi]です。|내일은 제 [생일~saengil]이에요.'),
'party_event':('a birthday party, not a political group or legal party',
'The birthday [party] is tonight.|La [fiesta] de cumpleaños es esta noche.|La [fête] d’anniversaire est ce soir.|Die [Feier] zum Geburtstag ist heute Abend.|La [festa] di compleanno è stasera.|A [festa] de aniversário é hoje à noite.|[حفل~ḥafl] عيد الميلاد هذا المساء.|生日[派对~pàiduì]在今晚。|誕生日[パーティー~pātī]は今夜です。|생일 [파티~pati]는 오늘 밤이에요.'),
'homework_assignment':('school homework that has been completed',
'I finished my [homework].|Terminé mis [deberes].|J’ai fini mes [devoirs].|Ich habe meine [Hausaufgaben] fertig.|Ho finito i [compiti].|Terminei a [lição de casa].|أنهيت [واجب~wājib]ي المدرسي.|我做完了[作业~zuòyè]。|[宿題~shukudai]が終わりました。|[숙제~sukje]를 끝냈어요.'),
'internet_network':('the internet as a network connection',
'The [internet] connection is slow.|La conexión a [internet] es lenta.|La connexion [Internet] est lente.|Die Verbindung zum [Internet] ist langsam.|La connessione [internet] è lenta.|A conexão com a [internet] está lenta.|اتصال ال[إنترنت~intarnit] بطيء.|[互联网~hùliánwǎng]连接很慢。|[インターネット~intānetto]接続が遅いです。|[인터넷~inteonet] 연결이 느려요.'),
'charger_device':('a charger for a phone battery',
'Where is the phone [charger]?|¿Dónde está el [cargador] del teléfono?|Où est le [chargeur] du téléphone ?|Wo ist das [Ladegerät] fürs Telefon?|Dov’è il [caricabatterie] del telefono?|Onde está o [carregador] do telefone?|أين [شاحن~shāḥin] الهاتف؟|手机[充电器~chōngdiànqì]在哪里？|携帯の[充電器~jūdenki]はどこですか。|휴대폰 [충전기~chungjeongi]가 어디예요?'),
'restaurant_place':('a restaurant serving food, not a home kitchen',
'The [restaurant] is near the hotel.|El [restaurante] está cerca del hotel.|Le [restaurant] est près de l’hôtel.|Das [Restaurant] ist in der Nähe des Hotels.|Il [ristorante] è vicino all’albergo.|O [restaurante] fica perto do hotel.|ال[مطعم~maṭʿam] قريب من الفندق.|[餐厅~cāntīng]在酒店附近。|[レストラン~resutoran]はホテルの近くにあります。|[식당~sikdang]은 호텔 근처에 있어요.'),
}


def routine_records():
    for record in records(DATA):
        record['provenance']['priority_basis']='NUS SMS development-only frequency priorities: daily schedules, school, communication and leisure; authored contexts, no reserved messages'
        yield record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);values=list(routine_records())
    with (a.output/'records.jsonl').open('x') as stream:
        for value in values:stream.write(canonical(value)+'\n')
    probe=protocol(values);probe['qa_run_id']='005';probe['scope']='Everyday routines development batch; no reserved SMS sentences used'
    (a.output/'phrase-protocol.json').write_text(json.dumps(probe,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'records':len(values),'concepts':len(DATA),'pairs':90,'linguistic_acceptance':False}))
