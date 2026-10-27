#!/usr/bin/env python3
"""Explicit common-life noun forms; training frequency guides topics only.

No evaluation text, automatic dictionary approval or inferred morphology.
A missing cell deliberately withholds a language/form requiring more context.
"""
import argparse
from pathlib import Path
from authored_everyday import mapping
from authored_people_ideas_units import LANGUAGES, forms
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

MEANINGS = {
 'thing':'a thing or things referred to as objects or matters, used as a noun',
 'day':'a day as a calendar period, not the sky or a cutting edge',
 'life':'human life and lived experience, used as a noun rather than a verb',
 'woman':'an adult woman or women, not a wife-specific or occupational title',
 'man':'an adult man or men, not a husband-specific title or the verb to staff',
 'country':'a country as a national territory, not countryside or a musical genre',
 'city':'a city as an urban settlement',
 'village':'a village as a small settlement',
 'language':'a human language as a system of communication, not a programming language or a tongue organ',
 'word':'a word or words as linguistic units, not the act of wording or an idiom',
 'education':'education as the process of teaching and learning',
 'service':'a service provided to people, used as a noun rather than the act of servicing equipment',
 'government':'a government as a governing administration',
 'challenge':'a challenge as a difficulty or demanding task, not the verb to dispute or issue a challenge',
 'health':'health as a state of bodily or mental wellbeing, not correctness of a claim',
 'business':'business as commercial activity, not a particular company or a private affair',
 'minute':'a minute as a sixty-second duration, not meeting records or the adjective meaning tiny',
}

# Same-number groups only. Chinese, Japanese, Korean and some Swahili nouns
# leave number unmarked. Tilde introduces a practical reading, not speech input.
DATA = {
 ('thing','singular'):'thing|cosa|chose|Ding|cosa|coisa|شيء~shayʾ|东西~dōngxi|もの~mono|것~geot|kitu',
 ('thing','plural'):'things|cosas|choses|Dinge|cose|coisas|أشياء~ashyāʾ|东西~dōngxi|もの~mono|것들~geotdeul/것~geot|vitu',
 ('day','singular'):'day|día|jour|Tag|giorno|dia|يوم~yawm|天~tiān|—|날~nal/일~il|siku',
 ('day','plural'):'days|días|jours|Tage|giorni|dias|أيام~ayyām|天~tiān|—|날들~naldeul/날~nal/일~il|siku',
 ('life','mass'):'life|vida|vie|Leben|vita|vida|حياة~ḥayāh|人生~rénshēng|人生~jinsei|삶~sam|maisha',
 ('woman','singular'):'woman|mujer|femme|Frau|donna|mulher|امرأة~imraʾa|女人~nǚrén|女性~josei|여자~yeoja|mwanamke',
 ('woman','plural'):'women|mujeres|femmes|Frauen|donne|mulheres|نساء~nisāʾ|女人~nǚrén/女人们~nǚrénmen|女性~josei|여자들~yeojadeul/여자~yeoja|wanawake',
 ('man','singular'):'man|hombre|homme|Mann|uomo|homem|رجل~rajul|男人~nánrén|男性~dansei|남자~namja|mwanamume',
 ('man','plural'):'men|hombres|hommes|Männer|uomini|homens|رجال~rijāl|男人~nánrén/男人们~nánrénmen|男性~dansei|남자들~namjadeul/남자~namja|wanaume',
 ('country','singular'):'country|país|pays|Land|paese|país|بلد~balad/دولة~dawla|国家~guójiā|国~kuni|나라~nara/국가~gukga|nchi',
 ('country','plural'):'countries|países|pays|Länder|paesi|países|بلدان~buldān/دول~duwal|国家~guójiā|国々~kuniguni/国~kuni|나라들~naradeul/나라~nara/국가~gukga|nchi',
 ('city','singular'):'city|ciudad|ville|Stadt|città|cidade|مدينة~madīna|城市~chéngshì|都市~toshi|도시~dosi|jiji',
 ('city','plural'):'cities|ciudades|villes|Städte|città|cidades|مدن~mudun|城市~chéngshì|都市~toshi|도시들~dosideul/도시~dosi|majiji',
 ('village','singular'):'village|aldea|village|Dorf|villaggio|aldeia|قرية~qarya|村庄~cūnzhuāng|村~mura|마을~maeul|kijiji',
 ('village','plural'):'villages|aldeas|villages|Dörfer|villaggi|aldeias|قرى~qurā|村庄~cūnzhuāng|村々~muramura/村~mura|마을들~maeuldeul/마을~maeul|vijiji',
 ('language','singular'):'language|idioma|langue|Sprache|lingua|idioma|لغة~lugha|语言~yǔyán|言語~gengo|언어~eoneo|lugha',
 ('language','plural'):'languages|idiomas|langues|Sprachen|lingue|idiomas|لغات~lughāt|语言~yǔyán|言語~gengo|언어들~eoneodeul/언어~eoneo|lugha',
 ('word','singular'):'word|palabra|mot|Wort|parola|palavra|كلمة~kalima|词语~cíyǔ/词~cí|言葉~kotoba|단어~daneo|neno',
 ('word','plural'):'words|palabras|mots|Wörter|parole|palavras|كلمات~kalimāt|词语~cíyǔ/词~cí|言葉~kotoba|단어들~daneodeul/단어~daneo|maneno',
 ('education','mass'):'education|educación|éducation|Bildung|istruzione|educação|تعليم~taʿlīm|教育~jiàoyù|教育~kyōiku|교육~gyoyuk|elimu',
 ('service','singular'):'service|servicio|service|Dienstleistung|servizio|serviço|خدمة~khidma|服务~fúwù|サービス~sābisu|서비스~seobiseu|huduma',
 ('service','plural'):'services|servicios|services|Dienstleistungen|servizi|serviços|خدمات~khadamāt|服务~fúwù|サービス~sābisu|서비스들~seobiseudeul/서비스~seobiseu|huduma',
 ('government','singular'):'government|gobierno|gouvernement|Regierung|governo|governo|حكومة~ḥukūma|政府~zhèngfǔ|政府~seifu|정부~jeongbu|serikali',
 ('government','plural'):'governments|gobiernos|gouvernements|Regierungen|governi|governos|حكومات~ḥukūmāt|政府~zhèngfǔ|政府~seifu|정부들~jeongbudeul/정부~jeongbu|serikali',
 ('challenge','singular'):'challenge|desafío|défi|Herausforderung|sfida|desafio|تحدي~taḥaddī|挑战~tiǎozhàn|課題~kadai|도전~dojeon|changamoto',
 ('challenge','plural'):'challenges|desafíos|défis|Herausforderungen|sfide|desafios|تحديات~taḥaddiyāt|挑战~tiǎozhàn|課題~kadai|도전들~dojeondeul/도전~dojeon|changamoto',
 ('health','mass'):'health|salud|santé|Gesundheit|salute|saúde|صحة~ṣiḥḥa|健康~jiànkāng|健康~kenkō|건강~geongang|afya',
 ('business','mass'):'business|comercio|commerce|Handel|commercio|comércio|تجارة~tijāra|商业~shāngyè|商売~shōbai|사업~saeop|biashara',
 ('minute','singular'):'minute|minuto|minute|Minute|minuto|minuto|دقيقة~daqīqa|分钟~fēnzhōng|—|분~bun|dakika',
 ('minute','plural'):'minutes|minutos|minutes|Minuten|minuti|minutos|دقائق~daqāʾiq|分钟~fēnzhōng|—|분~bun|dakika',
}


def permitted_source(topic, language):
    # These bare written forms have particularly common competing parts of
    # speech or senses. Targets remain possible from an unambiguous source.
    return not ((language=='en' and topic in {'man','word','service','challenge','minute'}) or
                (language=='zh' and topic in {'day','education','service','challenge','health'}) or
                (language=='ko' and topic in {'day','minute'}) or
                (language=='ar' and topic in {'health','minute'}) or
                (language in {'es','fr','de','pt'} and topic in {'woman','man'}) or
                (language in {'fr','it'} and topic=='language') or
                (language=='it' and topic=='country'))


def records():
    for (topic,number),line in DATA.items():
        parsed={language:forms(cell,language) for language,cell in zip(LANGUAGES,line.split('|'),strict=True) if cell!='—'}
        for source,lefts in parsed.items():
            if not permitted_source(topic,source):continue
            for target,rights in parsed.items():
                if source==target:continue
                for li,(left,_) in enumerate(lefts):
                    for ri,(right,reading) in enumerate(rights):
                        row=mapping('common_life_'+topic+'_'+number,source,target,left,right,left,right,MEANINGS[topic],reading)
                        row['logical_id']+=':'+str(li)+':'+str(ri)
                        row['usage'].update(context_extent='local_phrase',lexical_unit=True,whole_reference=False,
                            number_group=number,context_generalization='explicit complete common-life noun; no inferred inflection',
                            source_frame_span=row['source_span'][:],target_frame_span=row['target_span'][:],
                            source_frame_pattern=[{'focus':left}],target_frame_pattern=[{'focus':right}],
                            permitted_context=MEANINGS[topic]+'; unique corresponding full native forms must occur in the actual whole translation',
                            abstain_when=['Either complete counterpart is absent or repeated.',
                                'Competing meanings/readings, identifiers or invalid native boundaries exclude a match.',
                                'No unlisted morphology, articles, suffixes or grammar transformation is inferred.'])
                        row['provenance'].update(priority_basis='Common conversation topics; separate AfriSenti TRAIN-only frequencies for siku, huduma, wanawake, maisha, elimu, serikali and changamoto. No evaluation message read.',
                            form_source='Project-authored explicit forms and readings; dictionary frequency does not approve the mapping',
                            number_scope='Only listed corresponding number groups; some languages leave number unmarked',
                            whole_reference_eligibility='False: noun carriers cannot become whole-message translations')
                        validate(row);yield row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records());assert len(rows)==len({r['logical_id'] for r in rows})
    args.output.mkdir(parents=True,exist_ok=False);path=args.output/'records.jsonl'
    path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical({'records':len(rows),'concepts':len(MEANINGS),'number_groups':len(DATA),
        'records_sha256':digest_file(path),'authoring_source_sha256':digest_file(Path(__file__)),
        'author_assessment_pending':True,'release_ready':False}))
