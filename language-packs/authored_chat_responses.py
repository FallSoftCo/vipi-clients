#!/usr/bin/env python3
"""Explicit short replies that must work before language identification.

Project-authored development mappings. Only complete assessed responses gain a
whole-message reference. Embedded uses require the complete translated phrase.
"""
import argparse
from pathlib import Path
from authored_chat_openers import LANGUAGES, formula, focus, PUNCTUATION
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

DATA = {
 'yes': ('a positive answer or affirmation in a conversation',
  'Yes.|Sí.|Oui.|Ja.|Sì.|Sim.|نعم.~Naʿam.|是的。~Shì de.|はい。~Hai.|네.~Ne.|Ndiyo.'),
 'no': ('a negative answer or refusal in a conversation',
  'No.|No.|Non.|Nein.|No.|Não.|لا.~Lā.|不是。~Bú shì.|いいえ。~Iie.|아니요.~Aniyo.|Hapana.'),
 'okay': ('an acknowledgement that something is understood or acceptable',
  "Okay.|Vale.|D’accord.|In Ordnung.|Va bene.|Está bem.|حسنًا.~Ḥasanan.|好的。~Hǎo de.|わかりました。~Wakarimashita.|알겠어요.~Algesseoyo.|Sawa."),
 'please': ('a polite standalone request marker, not the verb to give pleasure',
  "Please.|Por favor.|S’il vous plaît.|Bitte.|Per favore.|Por favor.|رجاءً.~Rajāʾan.|请。~Qǐng.|お願いします。~Onegaishimasu.|—|Tafadhali."),
}
# Bare Chinese 不/不是 requires the proposition and its predicate to choose a
# grammatical negative answer. Do not supply it as a universal English "no".
OMITTED = {('no','zh'), ('please','zh'), ('please','de')}
ALIASES = {('yes','sw'):['Ndio.'], ('okay','en'):['OK.','Ok.'],
           ('okay','fr'):["D'accord."], ('please','fr'):["S'il vous plaît."]}


def forms(topic,language,sentence):
    values={sentence,sentence.rstrip(PUNCTUATION).rstrip()}
    for alternate in ALIASES.get((topic,language),[]):
        values.update((alternate,alternate.rstrip(PUNCTUATION).rstrip()))
    if language in ('en','es','fr','de','it','pt','sw'):
        values.update(v[:1].lower()+v[1:] for v in list(values))
    return sorted(values)


def cells(topic,line):
    return {language:formula(cell) for language,cell in zip(LANGUAGES,line.split('|'),strict=True)
            if cell!='—' and (topic,language) not in OMITTED}


def records():
    for topic,(meaning,line) in DATA.items():
        parsed=cells(topic,line)
        for source,(sentence,_) in parsed.items():
            for variant,original in enumerate(forms(topic,source,sentence)):
                for target,(translation,reading) in parsed.items():
                    if source==target:continue
                    row=mapping('chat_response_'+topic,source,target,focus(original),focus(translation),
                        original,translation,meaning,focus(reading) if reading else '')
                    row['logical_id']+=':'+str(variant)
                    row['usage'].update(context_extent='local_phrase',whole_reference=True,lexical_unit=True,
                        context_generalization='complete assessed short conversational response; no inferred predicate or omitted surrounding phrase',
                        source_frame_span=row['source_span'][:],target_frame_span=row['target_span'][:],
                        source_frame_pattern=[{'focus':row['source']}],target_frame_pattern=[{'focus':row['target']}],
                        permitted_context=meaning+'; embedded replacement requires the unique complete counterpart in the actual local translation',
                        abstain_when=['A complete counterpart is missing or repeats.',
                            'Conflicting meanings/readings, identifiers or invalid native boundaries prevent alignment.',
                            'An incomplete phrase or changed response cannot borrow the whole-message reference.'])
                    row['provenance'].update(priority_basis='Common first-chat replies, especially Swahili Ndiyo/Ndio, Hapana, Sawa and Tafadhali; no evaluation text read',
                        register_note='Conventional conversational responses, not a universal grammar rule. Chinese negative answers and isolated request markers are omitted; Korean standalone please is omitted because the proposed bare form conveys pleading. German Bitte is omitted because the isolated reply also commonly means you are welcome or pardon.')
                    validate(row);yield row


def readings():
    values={}
    for topic,(_,line) in DATA.items():
        for language,(sentence,reading) in cells(topic,line).items():
            if reading:values[(language,sentence)]=reading
    return [dict(language=language,text=sentence,latin=reading) for (language,sentence),reading in sorted(values.items())]


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records());assert len(rows)==len({r['logical_id'] for r in rows})
    args.output.mkdir(parents=True,exist_ok=False)
    p=args.output/'records.jsonl';p.write_text(''.join(canonical(r)+'\n' for r in rows))
    q=args.output/'sentence-readings.json';q.write_text(canonical(readings())+'\n')
    print(canonical(dict(records=len(rows),pairs=len({(r['source_language'],r['target_language']) for r in rows}),
        records_sha256=digest_file(p),readings=len(readings()),readings_sha256=digest_file(q),
        authoring_source_sha256=digest_file(Path(__file__)),author_assessment_pending=True,release_ready=False)))
