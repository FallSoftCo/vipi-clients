"""Exact present-form classification; no generated spellings or accent removal."""
import json,re
from collections import defaultdict
from build_wiktextract import EXCLUDED
RULE="attested-positive-present-verb-1"
POLICY="native-linked-attested-present-verbs-18"
SCHEMA="vipi-whole-present-verb-1"
LANGUAGES={"en","es","fr","de","pt"}
PEOPLE={"first-person":"1","second-person":"2","third-person":"3"}
NUMBERS={"singular":"s","plural":"p"}
ALLOWED={"present","indicative","first-person","second-person","third-person","singular","plural","informal","formal","vos-form","form-of"}
TENSE_CONFLICT={"past","preterite","preterit","imperfect","pluperfect","future","conditional"}
SUBJECTS={
 "en":{"i":{"1s"},"you":{"2s","2p"},"he":{"3s"},"she":{"3s"},"it":{"3s"},"we":{"1p"},"they":{"3p"}},
 "de":{"ich":{"1s"},"du":{"2s"},"er":{"3s"},"sie":{"3s","3p"},"es":{"3s"},"wir":{"1p"},"ihr":{"2p"}},
 "fr":{"je":{"1s"},"j'":{"1s"},"j’":{"1s"},"tu":{"2s"},"il":{"3s"},"elle":{"3s"},"on":{"3s"},"nous":{"1p"},"vous":{"2p"},"ils":{"3p"},"elles":{"3p"}},
 "es":{"yo":{"1s"},"tú":{"2s"},"vos":{"2s"},"él":{"3s"},"ella":{"3s"},"usted":{"3s"},"nosotros":{"1p"},"nosotras":{"1p"},"vosotros":{"2p"},"vosotras":{"2p"},"ellos":{"3p"},"ellas":{"3p"},"ustedes":{"3p"}},
 "pt":{"eu":{"1s"},"tu":{"2s"},"ele":{"3s"},"ela":{"3s"},"você":{"3s"},"nós":{"1p"},"vós":{"2p"},"eles":{"3p"},"elas":{"3p"},"vocês":{"3p"}}
}
def subject_people(text,start,language):
    # start is a UTF-16 boundary, as in both native clients.
    prefix=text.encode("utf-16-le")[:start*2].decode("utf-16-le")
    match=re.search(r"(?<![\w])([^\W\d_]+(?:['’])?)([ \t]*)$",prefix,re.UNICODE)
    if not match or (not match.group(2) and match.group(1).lower() not in {"j'","j’"}):return set()
    return SUBJECTS.get(language,{}).get(match.group(1).lower(),set())
def finite_people(features,text,start,language):
    # A possessive/article before a homograph such as "tu trabajo" provides
    # explicit noun evidence. Omitted subjects do not override that evidence.
    prefix=text.encode("utf-16-le")[:start*2].decode("utf-16-le")
    previous=re.search(r"(?<![\w])([^\W\d_]+)[ \t]+$",prefix,re.UNICODE)
    nominal={"es":{"el","la","los","las","un","una","unos","unas","mi","mis","tu","tus","su","sus","nuestro","nuestra","vuestro","vuestra","este","esta","ese","esa"},
             "pt":{"o","a","os","as","um","uma","uns","umas","meu","minha","teu","tua","seu","sua","nosso","nossa","vosso","vossa","este","esta","esse","essa"}}
    if previous and previous.group(1).lower() in nominal.get(language,set()):return set()
    if language=="en" and previous:
        before=prefix[:previous.start(1)]
        if re.search(r"(?i)(?<![\w])(?:did|didn['’]t|will|won['’]t|would|wouldn['’]t|can|can['’]t|could|couldn['’]t|shall|shan['’]t|should|shouldn['’]t|may|might|must|have|has|had|am|is|are|was|were)[ \t]+$",before):
            return set()
    people={f.removeprefix("present-person-") for f in features if f.startswith("present-person-")}
    subject=subject_people(text,start,language)
    if subject:return people & subject
    return set() if language in {"en","de","fr"} else people
def variants(head,raw,language):
    assert language in LANGUAGES
    grouped=defaultdict(list)
    for index,(written,tags) in enumerate(raw):
        if not 1<len(written)<=64 or not written.isalpha():continue
        grouped[written].append((index,set(json.loads(tags))))
    # A supplied English lexical head is also the non-third-singular present
    # spelling. Classify it; never synthesize an -s form. Exclude irregular be
    # and modal/auxiliary heads, and later withhold past-syncretic spellings.
    if language=="en" and head not in {"be","can","could","may","might","must","shall","should","will","would","ought"} and head.isalpha():
        grouped.setdefault(head,[])
    for written,rows in sorted(grouped.items()):
        modern=[tags for _,tags in rows if not tags&EXCLUDED]
        if any(tags&TENSE_CONFLICT for tags in modern):continue
        accepted=[(i,tags) for i,tags in rows if "present" in tags and tags<=ALLOWED and
            (language=="en" or "indicative" in tags)]
        people=set()
        for _,tags in accepted:
            persons={PEOPLE[t] for t in tags if t in PEOPLE}
            numbers={NUMBERS[t] for t in tags if t in NUMBERS}
            if language=="en" and numbers=={"p"} and not persons:persons={"1","2","3"}
            people.update(a+b for a in persons for b in numbers)
        classified_head=language=="en" and written==head and head not in {"be","can","could","may","might","must","shall","should","will","would","ought"}
        if classified_head:people.update({"1s","2s","1p","2p","3p"})
        if not people:continue
        yield dict(written=written,features=[RULE,"present","positive","active"]+
            ["present-person-"+p for p in sorted(people)],
            supplied=[dict(index=i,tags=sorted(tags)) for i,tags in rows],
            classified_english_head=classified_head)
