"""Exact author-reviewed dictionary contradictions for the pinned inventory.

These are individual meaning judgments, not independent accuracy certification.
Review again when upstream entry identities change.
"""
INVENTORY_SHA256 = "8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17"
REJECTIONS = {
    ("sw", 2168820, "b28657b739604b237b65cd34b5d3c903963202bdb8c1b890feb1e086fc7cdf29"): {
        "label": "to become stable",
        "headword": "imarisha",
        "native_definition": "Causative form of imara: to stabilize, to strengthen",
        "native_url": "https://en.wiktionary.org/wiki/imarisha#Swahili",
        "sense_url": "https://en.wiktionary.org/wiki/stabilize#English",
        "reason": "This causative verb makes or strengthens something into a stable state; the intransitive become-stable sense is a different relation.",
        "independent_semantic_acceptance": False,
    },
}

def rejected(language, identifier, sense, label):
    row = REJECTIONS.get((language, identifier, sense))
    if row is None:
        return False
    assert row["label"] == label, "The reviewed upstream sense label changed"
    return True

# Exact Korean entry definitions and English sense identities are shared here
# only to avoid repeating the same review text for each rejected relation.
KOREAN_REVIEWED_SENSES = {'1ddfeb73508b26bcbd32a41689350789dc3d344c5a0923bc6f7b72948bda626d': ('to expect or wait for a sound',
                                                                      'https://en.wiktionary.org/wiki/listen#English'),
 '20947fbf72bd58497083de329a3e316bbcb3f23e467c953bd4278b02ee80ed73': ('to perceive with the ear',
                                                                      'https://en.wiktionary.org/wiki/hear#English'),
 '4db7fe27d23f09fe549a764ac8888f41866de04afd00d0a6ab9bed6df56747bd': ('to put to use; to use or employ for a particular purpose, or in a '
                                                                      'particular case — see also use, employ, utilize',
                                                                      'https://en.wiktionary.org/wiki/apply#English'),
 '59a2183ce730fb864b5840885f7f0aeaaad0f07edd3b6f3b2940f3a6b83ebd4e': ('to accept advice or obey instruction',
                                                                      'https://en.wiktionary.org/wiki/listen#English'),
 '9204bbdd7fcac6b082f46ca1bbff325b6d460fed86d6906f8e639f17518eda8b': ('to pay attention to a sound',
                                                                      'https://en.wiktionary.org/wiki/listen#English'),
 '9eb9ddfa21db173edf922f17604c2915ec1cc24bb124b0963928c71b2372dc9c': ('field of study',
                                                                      'https://en.wiktionary.org/wiki/mathematics#English'),
 'a7f3a4df00d65b2ff5dfeb6700cb11dd362552d956bf53cf0a30f176140c4097': ('to pay out', 'https://en.wiktionary.org/wiki/spend#English'),
 'e85ce43533829ed7aad54536fcfcb85f339e002d64f7246d5dc1b713373aecd2': ('employ, apply', 'https://en.wiktionary.org/wiki/use#English'),
 'ea99ae91b9836c5417c12ba83f1478f456df3cadcef25552569e7c67e970af40': ('to form letters, etc.',
                                                                      'https://en.wiktionary.org/wiki/write#English'),
 'f1e9d34c5cd9d102e7522edcbf5fd44a967dffb1e90c2c4a75cc6ebaf4ae1ce4': ('to don', 'https://en.wiktionary.org/wiki/get#English')}
KOREAN_ENTRY_REVIEWS = {484940: {'headword': '쓰다',
          'native_definitions': ["to wear, to put on (a hat, helmet, etc., on one's head; a mask, pair of glasses, etc.)",
                                 "to put up, to hold (an umbrella over one's head)",
                                 'to be accused of, to be suspected of (an offence)',
                                 'to be covered (with dust, powder, etc.)'],
          'native_url': 'https://en.wiktionary.org/wiki/%EC%93%B0%EB%8B%A4#Korean',
          'rejected_senses': ['4db7fe27d23f09fe549a764ac8888f41866de04afd00d0a6ab9bed6df56747bd',
                              'a7f3a4df00d65b2ff5dfeb6700cb11dd362552d956bf53cf0a30f176140c4097',
                              'e85ce43533829ed7aad54536fcfcb85f339e002d64f7246d5dc1b713373aecd2',
                              'ea99ae91b9836c5417c12ba83f1478f456df3cadcef25552569e7c67e970af40']},
 484941: {'headword': '쓰다',
          'native_definitions': ['to write (in general)', 'to compose (a song, a piece of writing, etc.)'],
          'native_url': 'https://en.wiktionary.org/wiki/%EC%93%B0%EB%8B%A4#Korean',
          'rejected_senses': ['4db7fe27d23f09fe549a764ac8888f41866de04afd00d0a6ab9bed6df56747bd',
                              'a7f3a4df00d65b2ff5dfeb6700cb11dd362552d956bf53cf0a30f176140c4097',
                              'e85ce43533829ed7aad54536fcfcb85f339e002d64f7246d5dc1b713373aecd2',
                              'f1e9d34c5cd9d102e7522edcbf5fd44a967dffb1e90c2c4a75cc6ebaf4ae1ce4']},
 484942: {'headword': '쓰다',
          'native_definitions': ['to spend, to consume, to expend (money, time, resources, etc.)',
                                 'to speak (a language, a dialect, etc.)',
                                 'to hire, to employ',
                                 'to be appropriate, to be right'],
          'native_url': 'https://en.wiktionary.org/wiki/%EC%93%B0%EB%8B%A4#Korean',
          'rejected_senses': ['ea99ae91b9836c5417c12ba83f1478f456df3cadcef25552569e7c67e970af40',
                              'f1e9d34c5cd9d102e7522edcbf5fd44a967dffb1e90c2c4a75cc6ebaf4ae1ce4']},
 947557: {'headword': '듣다',
          'native_definitions': ['to drip, to drop (nowadays only of drops of liquid)'],
          'native_url': 'https://en.wiktionary.org/wiki/%EB%93%A3%EB%8B%A4#Korean',
          'rejected_senses': ['1ddfeb73508b26bcbd32a41689350789dc3d344c5a0923bc6f7b72948bda626d',
                              '20947fbf72bd58497083de329a3e316bbcb3f23e467c953bd4278b02ee80ed73',
                              '59a2183ce730fb864b5840885f7f0aeaaad0f07edd3b6f3b2940f3a6b83ebd4e',
                              '9204bbdd7fcac6b082f46ca1bbff325b6d460fed86d6906f8e639f17518eda8b']},
 1037860: {'headword': '수학',
           'native_definitions': ['study or learn (a discipline)', 'to pursue knowledge'],
           'native_url': 'https://en.wiktionary.org/wiki/%EC%88%98%ED%95%99#Korean',
           'rejected_senses': ['9eb9ddfa21db173edf922f17604c2915ec1cc24bb124b0963928c71b2372dc9c']}}

for _identifier, _entry in KOREAN_ENTRY_REVIEWS.items():
    for _sense in _entry["rejected_senses"]:
        _label, _url = KOREAN_REVIEWED_SENSES[_sense]
        REJECTIONS[("ko", _identifier, _sense)] = {
            "label": _label, "headword": _entry["headword"],
            "native_definitions": _entry["native_definitions"],
            "native_url": _entry["native_url"], "sense_url": _url,
            "reason": "This English relation belongs to a different same-spelling Korean entry. Preserve this native entry as competing evidence, but do not attach that other meaning to it.",
            "independent_semantic_acceptance": False,
        }
