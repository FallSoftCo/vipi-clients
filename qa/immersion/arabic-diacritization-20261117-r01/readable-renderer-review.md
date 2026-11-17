# Readable Arabic renderer comparison — dormant

The reference side renders supplied author-assessed vowels. The inference side renders what the probabilistic model predicted, including mistakes. A readable string is not proof the vowel prediction is right. Neither candidate is wired into production.

## msa_doctor
ذَهَبَ الطَّبِيبُ إِلَى الْمُسْتَشْفَى.
Reference guide: dhahaba aṭ-ṭabību ilā al-mustashfā.
Model metadata: ذَهَبَ الطَّبِيبُ إِلَى الْمُسْتَشْفَى.
Unaccepted model guide: dhahaba aṭ-ṭabību ilā al-mustashfā.

## msa_child_book
اِشْتَرَى الطِّفْلُ كِتَابًا جَدِيدًا.
Reference guide: ishtarā aṭ-ṭiflu kitāban jadīdan.
Model metadata: اشْتَرَى الطِّفْلُ كِتَابًا جَدِيدًا.
Unaccepted model guide: None

## msa_clean_water
نَحْتَاجُ إِلَى مَاءٍ نَظِيفٍ.
Reference guide: naḥtāju ilā mā'in naẓīfin.
Model metadata: نَحْتَاجُ إِلَى مَاءٍ نَظِيفٍ.
Unaccepted model guide: naḥtāju ilā mā'in naẓīfin.

## msa_room
أُرِيدُ حَجْزَ غُرْفَةٍ لِلَيْلَةٍ وَاحِدَةٍ.
Reference guide: urīdu ḥajza ghurfatin lilaylatin wāḥidatin.
Model metadata: أُرِيدَ حَجْزُ غُرْفَةٍ لِلَّيْلَةٍ وَاحِدَةٍ.
Unaccepted model guide: urīda ḥajzu ghurfatin lillaylatin wāḥidatin.

## msa_train
وَصَلَ الْقِطَارُ قَبْلَ الْمَغْرِبِ.
Reference guide: waṣala al-qiṭāru qabla al-maghribi.
Model metadata: وَصَلَ الْقِطَارُ قَبْلَ الْمَغْرِبِ.
Unaccepted model guide: waṣala al-qiṭāru qabla al-maghribi.

## msa_farmer
زَرَعَ الْفَلَّاحُ الْقَمْحَ.
Reference guide: zara'a al-fallāḥu al-qamḥa.
Model metadata: زَرْعُ الْفَلَاحِ الْقَمْحَ.
Unaccepted model guide: zar'u al-falāḥi al-qamḥa.

## msa_apartment
هَذِهِ شَقَّةٌ قَرِيبَةٌ مِنَ النَّهْرِ.
Reference guide: hādhihi shaqqatun qarībatun mina an-nahri.
Model metadata: هَذِهِ شِقَّةٌ قَرِيبَةٌ مِنَ النَّهْرِ.
Unaccepted model guide: hādhihi shiqqatun qarībatun mina an-nahri.

## msa_guard_closed
أَغْلَقَ الْحَارِسُ الْبَابَ.
Reference guide: aghlaqa al-ḥārisu al-bāba.
Model metadata: أَغْلَقَ الْحَارِسُ الْبَابَ.
Unaccepted model guide: aghlaqa al-ḥārisu al-bāba.

## msa_sleep
يَنَامُ الطِّفْلُ فِي الْغُرْفَةِ.
Reference guide: yanāmu aṭ-ṭiflu fī al-ghurfati.
Model metadata: يَنَامُ الطِّفْلُ فِي الْغُرْفَةِ.
Unaccepted model guide: yanāmu aṭ-ṭiflu fī al-ghurfati.

## msa_read
تَقْرَأُ الْمُعَلِّمَةُ رِسَالَةً قَصِيرَةً.
Reference guide: taqra'u al-mu'allimatu risālatan qaṣīratan.
Model metadata: تَقْرَأُ الْمُعَلِّمَةُ رِسَالَةً قَصِيرَةً.
Unaccepted model guide: taqra'u al-mu'allimatu risālatan qaṣīratan.

## polyphone_flag
رَفَعَ الْعَامِلُ الْعَلَمَ.
Reference guide: rafa'a al-'āmilu al-'alama.
Model metadata: رَفْعَ الْعَامِلِ الْعِلْمَ.
Unaccepted model guide: raf'a al-'āmili al-'ilma.

## polyphone_knowledge
يُحِبُّ الطَّالِبُ الْعِلْمَ.
Reference guide: yuḥibbu aṭ-ṭālibu al-'ilma.
Model metadata: يُحِبُّ الطَّالِبُ الْعِلْمَ.
Unaccepted model guide: yuḥibbu aṭ-ṭālibu al-'ilma.

## msa_king
الْمَلِكُ يَعِيشُ فِي الْقَصْرِ.
Reference guide: al-maliku ya'īshu fī al-qaṣri.
Model metadata: الْمَلِكُ يَعِيشُ فِي الْقَصْرِ.
Unaccepted model guide: al-maliku ya'īshu fī al-qaṣri.

## msa_queue
نَنْتَظِرُ فِي طَابُورٍ طَوِيلٍ.
Reference guide: nantaẓiru fī ṭābūrin ṭawīlin.
Model metadata: نَنْتَظِرُ فِي طَابُورٍ طَوِيلٍ.
Unaccepted model guide: nantaẓiru fī ṭābūrin ṭawīlin.

## msa_phone
هَذَا الْهَاتِفُ مَكْسُورٌ.
Reference guide: hādhā al-hātifu maksūrun.
Model metadata: هَذَا الْهَاتِفُ مَكْسُورٌ.
Unaccepted model guide: hādhā al-hātifu maksūrun.

## msa_garden
الْحَدِيقَةُ جَمِيلَةٌ فِي الرَّبِيعِ.
Reference guide: al-ḥadīqatu jamīlatun fī ar-rabī'i.
Model metadata: الْحَدِيقَةُ جَمِيلَةٌ فِي الرَّبِيعِ.
Unaccepted model guide: al-ḥadīqatu jamīlatun fī ar-rabī'i.

## Separate model ambiguity/dialect/name/coverage review

ambiguous_person (source_ambiguity): سَافَرَتْ أَمْسِ.
Unaccepted guide: sāfarat amsi.

ambiguous_you (source_ambiguity): هَلْ يُمْكِنُكَ فَتْحُ النَّافِذَةِ؟
Unaccepted guide: hal yumkinuka fatḥu an-nāfidhati؟

name_layla (names): أَرْسَلَتْ لَيْلَى رِسَالَةً إِلَى سُلَيْمٍ.
Unaccepted guide: arsalat laylā risālatan ilā sulaymin.

name_nura (names): نُورَةٌ تَنْتَظِرُ يُوسُفَ قُرْبَ الْجَامِعَةِ.
Unaccepted guide: nūratun tantaẓiru yūsufa qurba al-jāmi'ati.

dialect_egy (dialect): فِينَ أَقْرَبُ مَحَطَّةٍ؟
Unaccepted guide: fīna aqrabu maḥaṭṭatin؟

dialect_levant (dialect): شُوْ بَدَكَ تَشْرَبُ؟
Unaccepted guide: shuw badaka tashrabu؟

mixed_latin (mixed): قَابَلَتْ José قُرْبَ café فِي 8:30.
Unaccepted guide: qābalat José qurba café fī 8:30.

existing_marks (preservation): عَلِمَ سَامِرِ الْخَبَرَ الْيَوْمَ.
Unaccepted guide: 'alima sāmiri al-khabara al-yawma.

zero_width (preservation): أُحَبُّ الْقَهْوَةَ‍ كَثِيرًا.
Unaccepted guide: uḥabbu al-qahwata‍ kathīran.

url (preservation): افْتَحِ https://example.test/عربي?q=علم الْآنَ.
Unaccepted guide: None

code (preservation): اُكْتُبْ `علم_2026` فِي notes.md.
Unaccepted guide: uktub `علم_2026` fī notes.md.

persian_variants (variant): هَذِهِ کَافِیَةٌ.
Unaccepted guide: None
