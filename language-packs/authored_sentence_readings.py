#!/usr/bin/env python3
"""Explicit full-sentence Latin readings of the pinned authored references.

This is author assessment, not independent linguistic acceptance. No generic
Han conversion, Arabic vowel invention, IPA or model-generated runtime reading.
Rows follow sorted English references in the exact content-bound catalog below.
Export pairs the original written sentence with its reading for native lookup.
"""
import argparse
import json
from pathlib import Path
import unicodedata
from build_wiktextract import canonical, digest_file

CATALOG_SHA256 = '6eedd0b7d04fa82c905c648f35824d747ac87c9da6945f3caf4a1799ed0fb20a'
READINGS = {
 'ar': '''Al-fuṭūr jāhiz.
Al-'ashā' jāhiz.
Anā ashrab al-qahwa al-ān.
Anā ashrab ash-shāy al-ān.
Anā ashrab al-mā' al-ān.
Anā ākul al-khubz al-ān.
Anā ākul al-jubn al-ān.
Anā astami' ilā al-mūsīqā al-ān.
Anā a'zif 'alā al-biyānū al-ān.
Anā aqra' kitāban al-ān.
Anā atamashshā ma'a al-kalb al-ān.
Anā ushāhid filman al-ān.
Anā ma'a kalbī.
Ishtaraytu tadhkirat qiṭār.
Laysa ladayya mā yakfī min al-māl.
Anhaytu wājibī al-madrasī.
Ladayya ḥisāb bankī.
Ladayya su'āl.
Ladayya akhbār jayyida.
Anā uḥibb al-mūsīqā.
Aḥtāj ilā musā'ada.
Aḥtāj ilā mazīd min al-waqt.
Arsaltu risāla.
Arsaltu risālat barīd iliktrūnī.
Adrus fī aṣ-ṣabāḥ.
Iltaqaṭtu ṣūra.
A'mal fī al-layl.
'Amiltu ams.
Anā fī al-bayt.
Anā fī al-maktab.
Anā mutafarriġ fī nihāyat al-usbū' hādhihi.
Astami' ilā al-mūsīqā.
Abḥath 'an waẓīfa.
Sa'antaqil fī ash-shahr al-qādim.
Aqra' kitāban.
A'mal al-yawm.
A'mal ġadan.
Al-ġadā' jāhiz.
'Īd mīlādī ġadan.
Ṣadīqī hunā.
Aġliq al-bāb min faḍlik.
Narāka fī al-usbū' al-qādim.
Al-ḥaqība 'alā aṭ-ṭāwila.
Ḥafl 'īd al-mīlād ġadan.
Ḥafl 'īd al-mīlād hādhā al-masā'.
Al-ḥāfila muta'akhkhira.
As-sayyāra fī al-khārij.
Tabda' al-ḥiṣṣa qarīban.
Al-funduq qarīb min al-maṭār.
Ġurfat al-funduq hādi'a.
Lil-bayt ḥadīqa.
Ittiṣāl al-intarnit baṭī'.
Yabda' al-ijtimā' 'inda aẓ-ẓuhr.
Kānat al-mukālama al-hātifiyya qaṣīra.
Al-hātif yarinn.
As-si'r murtafi' jiddan.
Tawaqqafa al-maṭar.
Al-maṭ'am qarīb min al-funduq.
Al-imtiḥān al-madrasī ġadan.
Al-madrasa qarība min al-ḥadīqa.
Yashraḥ al-mu'allim ad-dars.
Al-qiṭār muta'akhkhir.
Yaqra' aṭ-ṭālib al-jāmi'ī kitāban.
Aṭ-ṭaqs jamīl.
Hunāka mushkila.
Intaqalnā ilā hunā al-'ām al-māḍī.
Naḥtāj ilā mazīd min aṭ-ṭa'ām.
Shāhadnā filman.
Naḥnu dhāhibūn ilā al-maṭār.
Mā 'unwān al-funduq?
Mā khuṭṭat ar-riḥla?
Mā raqam al-hātif al-khāṣṣ bik?
Ayna mawqif al-ḥāfila?
Ayna miftāḥ al-bāb?
Ayna shāḥin al-hātif?
Ayna maḥaṭṭat al-qiṭār?''',
 'ko': '''Achim siksaga junbidwaesseoyo.
Jeonyeok siksaga junbidwaesseoyo.
Jigeum keopireul masigo isseoyo.
Jigeum chareul masigo isseoyo.
Jigeum mureul masigo isseoyo.
Jigeum ppangeul meokgo isseoyo.
Jigeum chijeureul meokgo isseoyo.
Jigeum eumageul deutgo isseoyo.
Jigeum pianoreul chigo isseoyo.
Jigeum chaegeul ilgo isseoyo.
Jigeum gaereul sanchaeksikigo isseoyo.
Jigeum yeonghwareul bogo isseoyo.
Je gaewa hamkke isseoyo.
Gichapyoreul sasseoyo.
Doni bujokhaeyo.
Sukjereul kkeunnaesseoyo.
Eunhaeng gyejwaga isseoyo.
Jilmuni isseoyo.
Joeun sosigi isseoyo.
Jeoneun eumageul joahaeyo.
Doumi piryohaeyo.
Sigani deo piryohaeyo.
Mesijireul bonaesseoyo.
Imeireul bonaesseoyo.
Achime gongbuhaeyo.
Sajineul jjigeosseoyo.
Bame ilhaeyo.
Eojeneun ilhaesseoyo.
Jibe isseoyo.
Samusire isseoyo.
Ibeon jumare sigani isseoyo.
Eumageul deutgo isseoyo.
Iljarireul chatgo isseoyo.
Daeum dare isahaeyo.
Chaegeul ilgo isseoyo.
Oneureun ilhaeyo.
Naeireun ilhaeyo.
Jeomsimi junbidwaesseoyo.
Naeireun je saengirieyo.
Je gajogeun geuncheoe sarayo.
Je chinguga yeogi isseoyo.
Muneul dada juseyo.
Daeum jue mannayo.
Gabangi takja wie isseoyo.
Saengil patineun naeirieyo.
Saengil patineun oneul bamieyo.
Beoseuga neujeoyo.
Jadongchaneun bakke isseoyo.
Sueobi got sijakhaeyo.
Hoteleun gonghang geuncheoe isseoyo.
Hotel bangi joyonghaeyo.
Geu jibeneun jeongwoni isseoyo.
Inteonet yeongyeori neuryeoyo.
Hoeuineun jeongoe sijakhaeyo.
Tonghwaga jjalbasseoyo.
Jeonhwaga ulligo isseoyo.
Gagyeogi neomu nopayo.
Biga geuchyeosseoyo.
Sikdangeun hotel geuncheoe isseoyo.
Hakgyo siheomeun naeirieyo.
Hakgyoneun gongwon geuncheoe isseoyo.
Seonsaengnimi sueop naeyongeul seolmyeonghaeyo.
Gichaga neujeoyo.
Daehakgyo haksaengi chaegeul ilgo isseoyo.
Nalssiga joayo.
Munjega isseoyo.
Urineun jangnyeone yeogiro isahaesseoyo.
Eumsigi deo piryohaeyo.
Yeonghwareul bwasseoyo.
Gonghange gago isseoyo.
Hotel jusoga mwoyeyo?
Yeohaeng gyehoegi mwoyeyo?
Dangsinui jeonhwabeonhoga mwoyeyo?
Beoseu jeongnyujangi eodiyeyo?
Mun yeolsoega eodiyeyo?
Hyudaepon chungjeongiga eodiyeyo?
Gichayeogi eodiyeyo?''',
 'ja': '''Chōshoku ga dekimashita.
Yūshoku ga dekimashita.
Ima, kōhī o nonde imasu.
Ima, ocha o nonde imasu.
Ima, mizu o nonde imasu.
Ima, pan o tabete imasu.
Ima, chīzu o tabete imasu.
Ima, ongaku o kiite imasu.
Ima, piano o hiite imasu.
Ima, hon o yonde imasu.
Ima, inu o sanpo sasete imasu.
Ima, eiga o mite imasu.
Watashi no inu to issho ni imasu.
Densha no kippu o kaimashita.
Okane ga tarimasen.
Shukudai ga owarimashita.
Ginkō kōza o motte imasu.
Shitsumon ga arimasu.
Ii shirase ga arimasu.
Watashi wa ongaku ga suki desu.
Tasuke ga hitsuyō desu.
Motto jikan ga hitsuyō desu.
Messēji o okurimashita.
Mēru o okurimashita.
Asa ni benkyō shimasu.
Shashin o torimashita.
Yoru ni hataraite imasu.
Kinō wa shigoto deshita.
Ie ni imasu.
Jimusho ni imasu.
Konshūmatsu wa hima desu.
Ongaku o kiite imasu.
Shigoto o sagashite imasu.
Raigetsu hikkoshimasu.
Hon o yonde imasu.
Kyō wa shigoto desu.
Ashita wa shigoto desu.
Chūshoku ga dekimashita.
Ashita wa watashi no tanjōbi desu.
Watashi no kazoku wa chikaku ni sunde imasu.
Watashi no tomodachi wa koko ni imasu.
Doa o shimete kudasai.
Raishū aimashō.
Kaban wa tēburu no ue ni arimasu.
Tanjōbi pātī wa ashita desu.
Tanjōbi pātī wa kon'ya desu.
Basu ga okurete imasu.
Kuruma wa soto ni arimasu.
Jugyō ga mō sugu hajimarimasu.
Hoteru wa kūkō no chikaku ni arimasu.
Hoteru no heya wa shizuka desu.
Sono ie ni wa niwa ga arimasu.
Intānetto setsuzoku ga osoi desu.
Kaigi wa shōgo ni hajimarimasu.
Tsūwa wa mijikakatta desu.
Denwa ga natte imasu.
Nedan ga takasugimasu.
Ame ga yamimashita.
Resutoran wa hoteru no chikaku ni arimasu.
Gakkō no shiken wa ashita desu.
Gakkō wa kōen no chikaku ni arimasu.
Sensei ga jugyō no naiyō o setsumei shimasu.
Ressha ga okurete imasu.
Daigaku no gakusei ga hon o yonde imasu.
Tenki ga ii desu.
Mondai ga arimasu.
Kyonen koko ni hikkoshimashita.
Motto tabemono ga hitsuyō desu.
Eiga o mimashita.
Kūkō ni ikimasu.
Hoteru no jūsho wa nan desu ka.
Ryokō no keikaku wa nan desu ka.
Anata no denwa bangō wa nan desu ka.
Basutei wa doko desu ka.
Doa no kagi wa doko desu ka.
Keitai no jūdenki wa doko desu ka.
Eki wa doko desu ka.''',
 'zh': '''Zǎocān zhǔnbèi hǎo le.
Wǎnfàn zhǔnbèi hǎo le.
Wǒ zhèngzài hē kāfēi.
Wǒ zhèngzài hē chá.
Wǒ zhèngzài hē shuǐ.
Wǒ zhèngzài chī miànbāo.
Wǒ zhèngzài chī nǎilào.
Wǒ zhèngzài tīng yīnyuè.
Wǒ zhèngzài tán gāngqín.
Wǒ zhèngzài dú yì běn shū.
Wǒ zhèngzài liù gǒu.
Wǒ zhèngzài kàn yí bù diànyǐng.
Wǒ hé wǒ de gǒu zài yìqǐ.
Wǒ mǎi le yì zhāng huǒchēpiào.
Wǒ de qián bú gòu.
Wǒ zuò wán le zuòyè.
Wǒ yǒu yí ge yínháng zhànghù.
Wǒ yǒu yí ge wèntí.
Wǒ yǒu hǎo xiāoxi.
Wǒ xǐhuan yīnyuè.
Wǒ xūyào bāngzhù.
Wǒ xūyào gèng duō shíjiān.
Wǒ fā le yì tiáo xiāoxi.
Wǒ fā le yì fēng diànzǐ yóujiàn.
Wǒ zài zǎoshang xuéxí.
Wǒ pāi le yì zhāng zhàopiàn.
Wǒ zài yèjiān gōngzuò.
Wǒ zuótiān shàngbān le.
Wǒ zài jiā.
Wǒ zài bàngōngshì.
Zhè ge zhōumò wǒ yǒu kòng.
Wǒ zài tīng yīnyuè.
Wǒ zài zhǎo gōngzuò.
Wǒ xià ge yuè bānjiā.
Wǒ zài dú yì běn shū.
Wǒ jīntiān shàngbān.
Wǒ míngtiān shàngbān.
Wǔfàn zhǔnbèi hǎo le.
Míngtiān shì wǒ de shēngrì.
Wǒ de jiārén zhù zài fùjìn.
Wǒ de péngyou zài zhèlǐ.
Qǐng guān mén.
Xià zhōu jiàn.
Bāo zài zhuōzi shang.
Shēngrì pàiduì zài míngtiān.
Shēngrì pàiduì zài jīnwǎn.
Gōngjiāochē wǎndiǎn le.
Qìchē zài wàimian.
Kè kuài kāishǐ le.
Jiǔdiàn zài jīchǎng fùjìn.
Jiǔdiàn de fángjiān hěn ānjìng.
Zhè zuò fángzi yǒu yí ge huāyuán.
Hùliánwǎng liánjiē hěn màn.
Huìyì zhōngwǔ kāishǐ.
Zhè cì tōnghuà hěn duǎn.
Diànhuà xiǎng le.
Jiàgé tài gāo le.
Yǔ tíng le.
Cāntīng zài jiǔdiàn fùjìn.
Xuéxiào de kǎoshì zài míngtiān.
Xuéxiào zài gōngyuán fùjìn.
Lǎoshī zài jiǎng kè.
Huǒchē wǎndiǎn le.
Dàxué xuésheng zhèngzài kàn shū.
Tiānqì hěn hǎo.
Yǒu yí ge wèntí.
Wǒmen qùnián bān dào le zhèlǐ.
Wǒmen xūyào gèng duō shíwù.
Wǒmen kàn le yí bù diànyǐng.
Wǒmen yào qù jīchǎng.
Jiǔdiàn de dìzhǐ shì shénme?
Lǚxíng de jìhuà shì shénme?
Nǐ de diànhuà hàomǎ shì shénme?
Gōngjiāozhàn zài nǎlǐ?
Mén de yàoshi zài nǎlǐ?
Shǒujī chōngdiànqì zài nǎlǐ?
Huǒchēzhàn zài nǎlǐ?''',
}


def build(catalog, output):
    if digest_file(catalog) != CATALOG_SHA256: raise ValueError('Readings require their exact assessed source catalog')
    value = json.loads(catalog.read_text())
    if set(READINGS) != {'ar','zh','ja','ko'}: raise ValueError('Incomplete authoring batch')
    rows = []
    for language, lines in READINGS.items():
        references = sorted((r for r in value['references'] if r['pair'] == 'en-'+language), key=lambda r:r['original'])
        readings = lines.splitlines()
        if len(references) != len(readings): raise ValueError('Reading count differs for '+language)
        for reference, reading in zip(references, readings, strict=True):
            if not reading or len(reading) > 512 or not any(c.isalpha() for c in reading): raise ValueError('Invalid reading')
            for char in reading:
                if char.isalpha() and ('LATIN' not in unicodedata.name(char,'') or 0x0250 <= ord(char) <= 0x02ff):
                    raise ValueError('Non-readable script or IPA in reading')
            rows.append({'language':language,'text':reference['translation'],'latin':reading})
    rows.sort(key=lambda row:(row['language'],row['text']))
    if len({(r['language'],r['text']) for r in rows}) != len(rows): raise ValueError('Duplicate written target')
    result = {'schema':'vipi-sentence-readings-1','assessment':'author_assessment',
        'independent_linguistic_acceptance':False,'catalog_sha256':CATALOG_SHA256,
        'authoring_sha256':digest_file(Path(__file__)), 'entries':rows}
    with output.open('x') as stream: stream.write(canonical(result)+'\n')
    print(canonical({'readings':len(rows),'sha256':digest_file(output),'bytes':output.stat().st_size,'independent_linguistic_acceptance':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args(); build(args.catalog, args.output)
