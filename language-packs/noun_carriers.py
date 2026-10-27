"""Finite noun carriers. The noun changes language; its grammar stays in place.

Arabic uses an explicitly supplied singular definite form, with vowel marks
omitted as in ordinary Arabic writing. Korean uses nine standard noun particles.
These are lexical focus rules, never new whole-message translations/readings.
"""
from context_hints import lookup_key
from build_wiktextract import EXCLUDED

POLICY = "native-linked-noun-carriers-5"
KOREAN_RULE = "hangul-noun-particles-1"
ARABIC_RULE = "supplied-singular-definite-article-1"
REFERENCES = [
    "https://krdict.korean.go.kr/eng/dicSearch/SearchView?ParaWordNo=86111",
    "https://krdict.korean.go.kr/eng/dicSearch/SearchView?ParaWordNo=85851",
    "https://krdict.korean.go.kr/eng/dicSearch/SearchView?ParaWordNo=86355&nation=eng",
    "https://opentext.uoregon.edu/introarabic/chapter/the-definite-article-al/",
]


def korean(head, pos, tags):
    if pos != "noun" or set(tags) & (EXCLUDED | {"proper-noun", "plural", "dual"}):
        return []
    if not 1 <= len(head) <= 64 or not all(0xAC00 <= ord(c) <= 0xD7A3 for c in head):
        return []
    consonant = (ord(head[-1])-0xAC00) % 28 != 0
    endings = ["은" if consonant else "는", "이" if consonant else "가",
               "을" if consonant else "를", "과" if consonant else "와",
               "도", "만", "에", "에서", "의"]
    return [(head+ending, 0, len(head), 0, [KOREAN_RULE, "particle:"+ending])
            for ending in endings]


def arabic(head, form, pos, head_tags, form_tags):
    tags = set(form_tags)
    if pos != "noun" or (set(head_tags) | tags) & (EXCLUDED | {"proper-noun", "plural", "dual"}):
        return []
    if not {"definite", "singular"} <= tags:
        return []
    plain = lookup_key(head, "ar")
    if len(plain) < 2 or plain.startswith("ال") or not all(0x0620 <= ord(c) <= 0x064A for c in plain):
        return []
    carrier = lookup_key(form, "ar")
    if carrier != "ال"+plain:
        return []
    # Only the unmarked attested spelling is indexed with this offset. A
    # marked input cannot borrow these offsets: native carrier geometry checks
    # continue to require the exact stored spelling/UTF-16 length.
    return [(carrier, 2, len(carrier), 0, sorted(tags | {ARABIC_RULE}))]
