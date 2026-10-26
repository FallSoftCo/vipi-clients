#!/usr/bin/env python3
"""Complete short conversational formulas, including Vipi's namesake greeting.

Exact standalone messages also receive authored whole references. An embedded
formula requires the complete matching counterpart in the actual local
translation. No evaluation messages or generic grammar transforms are used.
"""
import argparse
from pathlib import Path
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file, readable_roman
from mapping_catalog import validate

LANGUAGES = ('en','es','fr','de','it','pt','ar','zh','ja','ko','sw')
# Native sentence ~ practical Latin reading (only for non-Roman languages).
DATA = {
    'hello': ('a friendly greeting to the other person',
        'Hello.|Hola.|Bonjour.|Hallo.|Salve.|Olá.|مرحبًا.~Marḥaban.|你好。~Nǐ hǎo.|こんにちは。~Konnichiwa.|안녕하세요.~Annyeonghaseyo.|Hujambo.'),
    'whats_up': ('a casual social check-in greeting, not a literal question about an upward direction',
        "What's up?|¿Qué tal?|Quoi de neuf ?|Was geht?|Come va?|E aí?|ما الأخبار؟~Mā al-akhbār?|最近怎么样？~Zuìjìn zěnmeyàng?|最近どう？~Saikin dō?|요즘 어때?~Yojeum eottae?|Mambo vipi?"),
    'thanks': ('an expression of gratitude to the other person',
        'Thanks.|Gracias.|Merci.|Danke.|Grazie.|Valeu.|شكرًا.~Shukran.|谢谢。~Xièxie.|ありがとう。~Arigatō.|고마워요.~Gomawoyo.|Asante.'),
    'thanks_a_lot': ('an intensified expression of gratitude, understood sincerely in this authored formula',
        'Thanks a lot.|Muchas gracias.|Merci beaucoup.|Vielen Dank.|Grazie mille.|Agradeço muito.|شكرًا جزيلًا.~Shukran jazīlan.|非常感谢。~Fēicháng gǎnxiè.|どうもありがとう。~Dōmo arigatō.|정말 고마워요.~Jeongmal gomawoyo.|Asante sana.'),
    'see_you_tomorrow': ('a farewell anticipating seeing the other person on the next calendar day',
        'See you tomorrow.|Hasta mañana.|À demain.|Bis morgen.|A domani.|Até amanhã.|إلى الغد.~Ilā al-ghad.|明天见。~Míngtiān jiàn.|また明日。~Mata ashita.|내일 봐요.~Naeil bwayo.|Tutaonana kesho.'),
}
# Alternate written input for the same complete formula. Target output remains
# the canonical sentence above, avoiding reverse-reference contradictions.
ALIASES = {('hello','en'):['Hi.'], ('thanks','en'):['Thank you.'],
    ('thanks_a_lot','en'):['Thank you very much.'], ('whats_up','en'):['What’s up?'],
    ('thanks','sw'):['Ahsante.'], ('thanks_a_lot','sw'):['Ahsante sana.']}
PUNCTUATION = '.!?。！？؟'


def formula(value):
    parts = value.split('~')
    if len(parts) not in (1,2): raise ValueError('One optional reading')
    if len(parts)==1: return parts[0], ''
    body=parts[1].rstrip('.!?').rstrip()
    reading=readable_roman(body)
    if not reading: raise ValueError('Missing readable Latin phrase')
    return parts[0], reading+parts[1][len(body):]


def focus(sentence):
    # Punctuation belongs to the original string, not the lexical replacement.
    return sentence.rstrip(PUNCTUATION).strip().lstrip('¿¡')


def source_forms(topic, language, sentence):
    values = {sentence, sentence.rstrip(PUNCTUATION).rstrip()}
    for alternate in ALIASES.get((topic,language), []):
        values.update((alternate, alternate.rstrip(PUNCTUATION).rstrip()))
    if language in ('en','es','fr','it','pt','sw'):
        values.update(value[:1].lower()+value[1:] for value in list(values))
    if language == 'es':
        values.update(value.lstrip('¿¡') for value in list(values))
        values.update(value[:1].lower()+value[1:] for value in list(values))
    return sorted(values)


def records():
    for topic, (meaning,line) in DATA.items():
        forms = dict(zip(LANGUAGES, map(formula,line.split('|')), strict=True))
        for source,(sentence,_) in forms.items():
            for variant,original in enumerate(source_forms(topic,source,sentence)):
                for target,(translation,reading) in forms.items():
                    if source==target: continue
                    if target in ('ar','zh','ja','ko') and not reading:
                        raise ValueError('Every non-Roman target requires an explicit reading')
                    row=mapping('chat_opener_'+topic,source,target,focus(original),focus(translation),
                        original,translation,meaning,focus(reading) if reading else '')
                    row['logical_id']+=':'+str(variant)
                    row['usage'].update(context_extent='local_phrase', whole_reference=True, lexical_unit=True,
                        context_generalization='complete assessed conversational formula; external grammar is never part of the replacement',
                        source_frame_span=row['source_span'][:], target_frame_span=row['target_span'][:],
                        source_frame_pattern=[{'focus':row['source']}], target_frame_pattern=[{'focus':row['target']}],
                        permitted_context=meaning+'; the complete unique native counterpart must occur in the actual local translation',
                        abstain_when=['Either complete native formula is absent.',
                            'Repeated occurrences, conflicting meanings/readings, protected literals or invalid native boundaries prevent alignment.',
                            'A differently conjugated or partially matching phrase must not borrow this formula.'])
                    row['provenance']['priority_basis']='First-chat greeting/thanks/farewell coverage, including the product namesake; no evaluation messages read'
                    row['provenance']['register_note']='Conventional friendly conversational equivalents; politeness and greeting customs differ by language. Broad goodbye formulas are omitted because some require knowing which person is leaving.'
                    validate(row);yield row


def readings():
    values={}
    for _,line in DATA.values():
        for language,(sentence,reading) in zip(LANGUAGES,map(formula,line.split('|')),strict=True):
            if reading:
                key=(language,sentence)
                if key in values and values[key]!=reading: raise ValueError('Conflicting sentence reading')
                values[key]=reading
    assert len(values)==20
    return [{'language':language,'text':sentence,'latin':reading} for (language,sentence),reading in sorted(values.items())]


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records());assert len({r['logical_id'] for r in rows})==len(rows)
    args.output.mkdir(parents=True,exist_ok=False)
    output=args.output/'records.jsonl';output.write_text(''.join(canonical(row)+'\n' for row in rows))
    reading_path=args.output/'sentence-readings.json';reading_path.write_text(canonical(readings())+'\n')
    print(canonical({'records':len(rows),'pairs':len({(r['source_language'],r['target_language']) for r in rows}),
        'records_sha256':digest_file(output),'readings':len(readings()),'readings_sha256':digest_file(reading_path),
        'authoring_source_sha256':digest_file(Path(__file__)),'release_ready':False}))
