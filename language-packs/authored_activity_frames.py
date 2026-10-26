"""Explicit daily-activity constructions, authored development data only.

These noun focuses deliberately exclude articles, particles and verb/person
morphology. No held-out dialogue or provider output supplies their wording.
"""

ACTIVITY_TEMPLATES = [
    'I am {f} now.', 'Estoy {f} ahora.', 'Je {f} maintenant.', 'Ich {f} gerade.',
    'Sto {f} adesso.', 'Estou {f} agora.', 'أنا {f} الآن.', '我正在{f}。',
    '今、{f}。', '지금 {f}.',
]

DATA = {
    'drinking_coffee': (
        'coffee consumed as a beverage, not the plant or a cafe establishment',
        ACTIVITY_TEMPLATES,
        ['drinking [coffee]', 'bebiendo [café]', 'bois du [café]', 'trinke [Kaffee]',
         'bevendo [caffè]', 'bebendo [café]', 'أشرب ال[قهوة~qahwa]', '喝[咖啡~kāfēi]',
         '[コーヒー~kōhī]を飲んでいます', '[커피~keopi]를 마시고 있어요']),
    'drinking_tea': (
        'tea consumed as a beverage, not the plant or a meal called tea',
        ACTIVITY_TEMPLATES,
        ['drinking [tea]', 'bebiendo [té]', 'bois du [thé]', 'trinke [Tee]',
         'bevendo [tè]', 'bebendo [chá]', 'أشرب ال[شاي~shāy]', '喝[茶~chá]',
         '[お茶~ocha]を飲んでいます', '[차~cha]를 마시고 있어요']),
    'eating_bread': (
        'bread eaten as food, not money or a verb', ACTIVITY_TEMPLATES,
        ['eating [bread]', 'comiendo [pan]', 'mange du [pain]', 'esse [Brot]',
         'mangiando [pane]', 'comendo [pão]', 'آكل ال[خبز~khubz]', '吃[面包~miànbāo]',
         '[パン~pan]を食べています', '[빵~ppang]을 먹고 있어요']),
    'eating_cheese': (
        'cheese eaten as food, not a photographic instruction or a figurative expression', ACTIVITY_TEMPLATES,
        ['eating [cheese]', 'comiendo [queso]', 'mange du [fromage]', 'esse [Käse]',
         'mangiando [formaggio]', 'comendo [queijo]', 'آكل ال[جبن~jubn]', '吃[奶酪~nǎilào]',
         '[チーズ~chīzu]を食べています', '[치즈~chijeu]를 먹고 있어요']),
    'listening_music': (
        'music being listened to as musical sound, not figurative music or a music score',
        [*ACTIVITY_TEMPLATES[:2], 'J’{f} maintenant.', *ACTIVITY_TEMPLATES[3:]],
        ['listening to [music]', 'escuchando [música]', 'écoute de la [musique]', 'höre [Musik]',
         'ascoltando [musica]', 'ouvindo [música]', 'أستمع إلى ال[موسيقى~mūsīqā]', '听[音乐~yīnyuè]',
         '[音楽~ongaku]を聴いています', '[음악~eumak]을 듣고 있어요']),
    'watching_movie': (
        'a movie being watched as an audiovisual work, not a material coating', ACTIVITY_TEMPLATES,
        ['watching a [movie]', 'viendo una [película]', 'regarde un [film]', 'sehe einen [Film]',
         'guardando un [film]', 'assistindo a um [filme]', 'أشاهد [فيلم~film]ًا', '看一部[电影~diànyǐng]',
         '[映画~eiga]を見ています', '[영화~yeonghwa]를 보고 있어요']),
    'playing_piano': (
        'a piano played as a musical instrument, not a quiet-dynamics instruction', ACTIVITY_TEMPLATES,
        ['playing the [piano]', 'tocando el [piano]', 'joue du [piano]', 'spiele [Klavier]',
         'suonando il [pianoforte]', 'tocando [piano]', 'أعزف على ال[بيانو~biyānū]', '弹[钢琴~gāngqín]',
         '[ピアノ~piano]を弾いています', '[피아노~piano]를 치고 있어요']),
    'walking_dog': (
        'a dog taken for a walk as an animal, not an insult, food or a mechanical part', ACTIVITY_TEMPLATES,
        ['walking the [dog]', 'paseando al [perro]', 'promène le [chien]', 'führe den [Hund] aus',
         'portando a spasso il [cane]', 'passeando com o [cachorro]', 'أتمشى مع ال[كلب~kalb]', '遛[狗~gǒu]',
         '[犬~inu]を散歩させています', '[개~gae]를 산책시키고 있어요']),
    'bank_account': (
        'an account held at a financial bank, not a narrative, user profile or river bank',
        ['I have a {f}.', 'Tengo una {f}.', 'J’ai un {f}.', 'Ich habe ein {f}.',
         'Ho un {f}.', 'Tenho uma {f}.', 'لدي {f}.', '我有一个{f}。', '{f}を持っています。', '{f} 있어요.'],
        ['bank [account]', '[cuenta] bancaria', '[compte] bancaire', '[Konto] bei einer Bank',
         '[conto] bancario', '[conta] bancária', '[حساب~ḥisāb] بنكي', '银行[账户~zhànghù]',
         '銀行[口座~kōza]', '은행 [계좌~gyejwa]가']),
    'train_station': (
        'a station serving railway trains, not a broadcast station or a social position',
        ['Where is {f}?', '¿Dónde está {f}?', 'Où est {f} ?', 'Wo ist {f}?',
         'Dov’è {f}?', 'Onde fica {f}?', '{f}؟', '{f}？', '{f}どこですか。', '{f} 어디예요?'],
        ['the [train station]', 'la [estación de tren]', 'la [gare ferroviaire]', 'der [Bahnhof]',
         'la [stazione ferroviaria]', 'a [estação de trem]', 'أين [محطة القطار~maḥaṭṭat al-qiṭār]',
         '[火车站~huǒchēzhàn]在哪里', '[駅~eki]は', '[기차역~gichayeok]이']),
    'bus_stop': (
        'a stopping place served by buses, not a verb, punctuation or a musical stop',
        ['Where is {f}?', '¿Dónde está {f}?', 'Où est {f} ?', 'Wo ist {f}?',
         'Dov’è {f}?', 'Onde fica {f}?', '{f}؟', '{f}？', '{f}どこですか。', '{f} 어디예요?'],
        ['the [bus stop]', 'la [parada de autobús]', 'l’[arrêt de bus]', 'die [Bushaltestelle]',
         'la [fermata dell’autobus]', 'o [ponto de ônibus]', 'أين [موقف الحافلة~mawqif al-ḥāfila]',
         '[公交站~gōngjiāozhàn]在哪里', '[バス停~basutei]は', '[버스 정류장~beoseu jeongnyujang]이']),
    'phone_number': (
        'a number identifying a telephone connection, not a count, musical number or generic identifier',
        ['What is {f}?', '¿Cuál es {f}?', 'Quel est {f} ?', 'Was ist {f}?',
         'Qual è {f}?', 'Qual é {f}?', 'ما {f}؟', '{f}是什么？',
         'あなたの{f}何ですか。', '당신의 {f} 뭐예요?'],
        ['your [phone number]', 'tu [número de teléfono]', 'ton [numéro de téléphone]', 'deine [Telefonnummer]',
         'il tuo [numero di telefono]', 'o seu [número de telefone]', '[رقم الهاتف~raqm al-hātif] الخاص بك',
         '你的[电话号码~diànhuà hàomǎ]', '[電話番号~denwa bangō]は', '[전화번호~jeonhwabeonho]가']),
    'liking_music': (
        'music as a musical art or sound that someone likes, not a score or figurative euphemism',
        ['I {f}.','Me {f}.','J’{f}.','Ich {f}.','Mi {f}.','Eu {f}.','أنا {f}.','我{f}。','私は{f}。','저는 {f}.'],
        ['like [music]','gusta la [música]','aime la [musique]','mag [Musik]','piace la [musica]',
         'gosto de [música]','أحب ال[موسيقى~mūsīqā]','喜欢[音乐~yīnyuè]','[音楽~ongaku]が好きです','[음악~eumak]을 좋아해요']),
    'possessed_dog': (
        'a dog referred to with an explicit possessor as an animal companion, not food or a mechanical part',
        ['I am with {f}.','Estoy con {f}.','Je suis avec {f}.','Ich bin mit {f} zusammen.',
         'Sono con {f}.','Estou com {f}.','أنا مع {f}.','我和{f}在一起。','{f}と一緒にいます。','{f} 함께 있어요.'],
        ['my [dog]','mi [perro]','mon [chien]','meinem [Hund]','il mio [cane]','meu [cachorro]',
         '[كلب~kalb]ي','我的[狗~gǒu]','私の[犬~inu]','제 [개~gae]와']),
}


def pattern(concept, language, focus):
    """Only checked finite alternatives; literal-only frames remain the default."""
    literal=lambda value: {'literal': value}
    slot=lambda values: {'slot': values}
    noun={'focus': focus}
    if concept=='liking_music':
        return {
            'en':[slot(['like ','likes ','love ','loves ','enjoy ','enjoys ']),noun],
            'es':[literal('gusta'),slot([' la ',' mucho la ']),noun],
            'fr':[slot(['aime','aimes','aiment','aimer','adore','adores','adorent','adorer']),literal(' la '),noun],
            'de':[slot(['mag ','mögen ','magst ','mögt ','liebe ','liebt ','lieben ']),noun],
            'it':[slot(['piace','amo','adoro','ami','ama','amano','adori','adora','adorano']),literal(' la '),noun],
            'pt':[slot(['gosto','gosta','gostamos','gostam','gostar']),literal(' de '),noun],
            'ja':[noun,literal('が'),slot(['好き','好きです','好きだ','大好き','大好きです','大好きだ'])],
            'ko':[noun,literal('을 좋아'),slot(['해요','해','한다','합니다','하는','하고','했어요'])],
        }.get(language)
    if concept=='possessed_dog':
        possessors={
            'en':['my','your','his','her','our','their'], 'es':['mi','tu','su','nuestro','vuestro'],
            'fr':['mon','ton','son','notre','votre','leur'],
            'de':['mein','meinen','meinem','dein','deinen','deinem','sein','seinen','seinem','ihr','ihren','ihrem','unser','unseren','unserem'],
            'it':['il mio','il tuo','il suo','il nostro','il vostro','il loro'],
            'pt':['meu','o meu','seu','o seu','nosso','o nosso','teu','o teu'],
        }
        if language in possessors:
            choices=possessors[language]
            return [slot([p+' ' for p in choices]+[p[0].upper()+p[1:]+' ' for p in choices]),noun]
        return {
            'ar':[noun,slot(['ي','ك','ه','ها','نا','هم','هن','كم','كن'])],
            'zh':[slot(['我的','你的','他的','她的','我们的','你们的','他们的']),noun],
            'ja':[slot(['私の','僕の','あなたの','彼の','彼女の','私たちの','彼らの','自分の']),noun],
            'ko':[slot(['제 ','내 ','너의 ','우리 ','그의 ','그녀의 ']),noun,slot(['와','는','가','를','의','도','에게'])],
        }.get(language)
    if concept in ('drinking_coffee', 'drinking_tea'):
        from authored_phrase_frames import pattern as original_pattern
        if language=='fr':
            return [literal('bo'),slot(['is','it','ire']),literal(' du '),noun]
        if language=='ko':
            return [noun,literal('를 '),slot(['마시고 있어요','마시고 있다','마시고있다','마셔요','마십니다'])]
        return original_pattern('drinking_water',language,focus)
    if concept in ('eating_bread','eating_cheese'):
        return {
            'en':[literal('eat'),slot(['ing ',' ','s ']),noun],
            'es':[literal('com'),slot(['iendo ','o ','es ','e ','emos ','en ','er ']),noun],
            'fr':[literal('mang'),slot(['e','es','ent','er']),literal(' du '),noun],
            'it':[literal('mangi'),slot(['ando ','o ','a ','amo ','ate ','ano ','are ']),noun],
            'pt':[literal('com'),slot(['endo ','o ','e ','emos ','em ','er ']),noun],
            'ja':[noun,literal('を'),slot(['食べています','食べている','食べてる','食べます','食べる','食べていた'])],
            'ko':[noun,literal('을 ' if concept=='eating_bread' else '를 '),slot(['먹고 있어요','먹고 있다','먹고있다','먹어요','먹습니다'])],
        }.get(language)
    if concept=='bank_account' and language=='ko':
        return [literal('은행 '),noun,slot(['가','는','를','에','의'])]
    if concept=='train_station' and language=='ko':
        return [noun,literal('이')]
    if concept=='bus_stop' and language=='ko':
        return [noun,literal('이')]
    if concept=='phone_number' and language=='ko':
        return [noun,literal('가')]
    return None
