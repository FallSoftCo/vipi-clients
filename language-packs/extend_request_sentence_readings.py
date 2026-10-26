#!/usr/bin/env python3
"""Add exact authored request readings without changing earlier assessments.

Input assets, both authoring sources and the reference catalog are hash-bound.
No runtime transliteration, corpus sentence, inferred name or unknown clause is
accepted. Audio continues to use the native sentence.
"""
import argparse
import json
from pathlib import Path
import unicodedata
import authored_needs_frames as needs
import authored_request_frames as requests
from authored_phrase_frames import parse
from build_wiktextract import canonical, digest_file

BASE_SHA = '3294a55d9928824abcce2b2fba5be4dea22febd6bff1e2722a406bde2fa8d5cd'
CATALOG_SHA = 'cb83b9696c77fd56e1fa384d2aec5a0dba3a34fa1fc48e817f2003ebcf00f2cf'
SOURCE_SHAS = {
    'authored_needs_frames.py':'11db9924b33b43502060eaa4a2ef99f88fbca335b070d0b1e042e14887ed0e02',
    'authored_request_frames.py':'f2554aad746126b6102e4ec9d9c7d4326c771a807dd8dd42eaebec7f2a5f0ab3',
}
LANGUAGES = ('ar','zh','ja','ko')

NEEDS = {
    'food': "Aḥtāj ilā ṭa'ām.|Wǒ xūyào shíwù.|Tabemono ga hitsuyō desu.|Eumsigi piryohaeyo.",
    'water': "Aḥtāj ilā mā'.|Wǒ xūyào shuǐ.|Mizu ga hitsuyō desu.|Muri piryohaeyo.",
    'money': 'Aḥtāj ilā māl.|Wǒ xūyào qián.|Okane ga hitsuyō desu.|Doni piryohaeyo.',
    'help': "Aḥtāj ilā musā'ada.|Wǒ xūyào bāngzhù.|Tasuke ga hitsuyō desu.|Doumi piryohaeyo.",
    'information': "Aḥtāj ilā ma'lūmāt.|Wǒ xūyào xìnxī.|Jōhō ga hitsuyō desu.|Jeongboga piryohaeyo.",
    'address': "Aḥtāj ilā 'unwān barīdī.|Wǒ xūyào yí ge yóujì dìzhǐ.|Yūsōsaki no jūsho ga hitsuyō desu.|Upyeon jusoga piryohaeyo.",
    'phone_number': 'Aḥtāj ilā raqam hātif.|Wǒ xūyào yí ge diànhuà hàomǎ.|Denwa bangō ga hitsuyō desu.|Jeonhwabeonhoga piryohaeyo.',
    'taxi': 'Aḥtāj ilā sayyārat ujra.|Wǒ xūyào yí liàng chūzūchē.|Takushī ga hitsuyō desu.|Taeksiga piryohaeyo.',
    'doctor': 'Aḥtāj ilā ṭabīb.|Wǒ xūyào yí wèi yīshēng.|Ishi ga hitsuyō desu.|Uisaga piryohaeyo.',
    'receipt': 'Aḥtāj ilā īṣāl.|Wǒ xūyào yì zhāng shōujù.|Ryōshūsho ga hitsuyō desu.|Yeongsujeungi piryohaeyo.',
    'phone_charger': 'Aḥtāj ilā shāḥin hātif.|Wǒ xūyào yí ge shǒujī chōngdiànqì.|Keitai denwa no jūdenki ga hitsuyō desu.|Hyudaepon chungjeongiga piryohaeyo.',
    'umbrella': 'Aḥtāj ilā miẓalla.|Wǒ xūyào yì bǎ yǔsǎn.|Kasa ga hitsuyō desu.|Usani piryohaeyo.',
    'door_key': 'Aḥtāj ilā miftāḥ bāb.|Wǒ xūyào yì bǎ mén yàoshi.|Doa no kagi ga hitsuyō desu.|Mun yeolsoega piryohaeyo.',
    'breakfast': 'Aḥtāj ilā fuṭūr.|Wǒ xūyào zǎocān.|Chōshoku ga hitsuyō desu.|Achim siksaga piryohaeyo.',
    'time': 'Aḥtāj ilā waqt iḍāfī.|Wǒ xūyào gèng duō shíjiān.|Motto jikan ga hitsuyō desu.|Deo maneun sigani piryohaeyo.',
    'rest': 'Aḥtāj ilā rāḥa.|Wǒ xūyào xiūxi.|Kyūsoku ga hitsuyō desu.|Hyusigi piryohaeyo.',
}
REQUESTS = {
    'restaurant_search': "Abḥath 'an maṭ'am.|Wǒ zài zhǎo cāntīng.|Resutoran o sagashite imasu.|Sikdangeul chatgo isseoyo.",
    'hotel_search': "Abḥath 'an funduq.|Wǒ zài zhǎo jiǔdiàn.|Hoteru o sagashite imasu.|Hoteleul chatgo isseoyo.",
    'job_search': "Abḥath 'an waẓīfa.|Wǒ zài zhǎo gōngzuò.|Shigoto o sagashite imasu.|Ireul chatgo isseoyo.",
    'send_message': 'Ursil risāla.|Wǒ zhèngzài fā xiāoxi.|Messēji o okutte imasu.|Mesijireul bonaego isseoyo.',
    'send_email': 'Ursil risālat barīd iliktrūnī.|Wǒ zhèngzài fā diànzǐ yóujiàn.|Mēru o okutte imasu.|Imeireul bonaego isseoyo.',
    'train_ticket_request': 'Aḥtāj ilā tadhkirat qiṭār.|Wǒ xūyào yì zhāng huǒchēpiào.|Ressha no kippu ga hitsuyō desu.|Gichapyoga piryohaeyo.',
    'hotel_room_request': 'Aḥtāj ilā ghurfat funduq.|Wǒ xūyào yì jiān jiǔdiàn fángjiān.|Hoteru no heya ga hitsuyō desu.|Hotel bangi piryohaeyo.',
}


def build(base, catalog, output):
    if digest_file(base) != BASE_SHA or digest_file(catalog) != CATALOG_SHA:
        raise ValueError('Exact assessed base and catalog required')
    for name, sha in SOURCE_SHAS.items():
        if digest_file(Path(__file__).with_name(name)) != sha:
            raise ValueError('Authoring source changed: ' + name)
    previous = json.loads(base.read_text())
    entries = {(row['language'],row['text']):row['latin'] for row in previous['entries']}
    if len(entries) != len(previous['entries']): raise ValueError('Duplicate base reading')
    references = {(r['pair'].split('-')[1], r['translation']) for r in json.loads(catalog.read_text())['references']}
    added = reused = 0
    for data, readings, templates in [(needs.DATA, NEEDS, needs.TEMPLATES), (requests.DATA, REQUESTS, None)]:
        if set(data) != set(readings): raise ValueError('Every topic requires explicit readings')
        for concept, values in data.items():
            _, patterns, line = (values[0],templates,values[1]) if templates else values
            written = {language:template.format(f=parse(marked)[0]) for language,template,marked
                       in zip(needs.LANGUAGES,patterns,line.split('|'),strict=True)}
            for language, latin in zip(LANGUAGES,readings[concept].split('|'),strict=True):
                key = language,written[language]
                if key not in references: raise ValueError('Reading lacks an assessed complete reference: '+str(key))
                if not latin or len(latin)>512: raise ValueError('Invalid reading')
                for char in latin:
                    if char.isalpha() and ('LATIN' not in unicodedata.name(char,'') or 0x0250<=ord(char)<=0x02ff):
                        raise ValueError('Native script or IPA in Latin reading')
                if key in entries:
                    if entries[key] != latin: raise ValueError('Conflicting assessment: '+str(key)+' / '+entries[key]+' / '+latin)
                    reused += 1
                else: entries[key] = latin; added += 1
    rows = [{'language':lang,'text':native,'latin':latin} for (lang,native),latin in sorted(entries.items())]
    result = {'schema':'vipi-sentence-readings-1', 'assessment':'author_assessment',
              'independent_linguistic_acceptance':False, 'catalog_sha256':CATALOG_SHA,
              'base_sha256':BASE_SHA, 'source_sha256':SOURCE_SHAS,
              'authoring_sha256':digest_file(Path(__file__)), 'entries':rows}
    with output.open('x') as f: f.write(canonical(result)+'\n')
    print(canonical({'readings':len(rows),'added':added,'identical_existing':reused,'sha256':digest_file(output),
                     'bytes':output.stat().st_size,'independent_linguistic_acceptance':False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True); p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args(); build(a.base,a.catalog,a.output)
