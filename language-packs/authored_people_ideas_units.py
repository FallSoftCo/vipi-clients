#!/usr/bin/env python3
"""Explicit everyday people and ideas vocabulary, with listed number forms.

These are lexical carriers, never whole-message translations. Singular/plural
groups pair only with the corresponding group. A language can leave number
unmarked; the actual whole translation still supplies the matching counterpart.
No evaluation transcript or automatic morphology supplies these forms.
"""
import argparse
from pathlib import Path

from authored_everyday import mapping
from authored_everyday_units import form_variants
from authored_conversation import DATA as CONTEXTS
from build_wiktextract import canonical, digest_file, readable_roman
from mapping_catalog import validate

LANGUAGES = ('en','es','fr','de','it','pt','ar','zh','ja','ko','sw')
MEANINGS = {
    'person': 'human persons, not a grammatical person or a corporation treated as a legal person',
    'child': 'a human child or children, not a computer node or a derived technical object',
    'mother': 'a mother as a human parent, not an equipment name or an idiom',
    'father': 'a father as a human parent, not a religious title or an idiom',
    'family': CONTEXTS['family'][0],
    'name': 'a name identifying a person or thing, used as a noun rather than the act of naming',
    'idea': 'an idea or thought proposed or considered, used as a noun',
    'reason': 'a reason explaining or justifying something, used as a noun',
    'example': 'an example illustrating something, used as a noun',
    'world': 'the world as the earth or human world, not the act of turning or a scholar',
    'story': 'a story as a narrative account, not a building floor or the academic study of history',
}
# All forms are written explicitly. Tilde introduces the practical Latin reading.
# Slash separates listed same-number alternatives, not inferred inflections.
DATA = {
    ('person','singular'): 'person|persona|personne|Person|persona|pessoa|شخص~shakhṣ|人~rén|人~hito|사람~saram|mtu',
    ('person','plural'): 'people/persons|personas/gente|personnes/gens|Personen/Menschen|persone/gente|pessoas/gente|أشخاص~ashkhāṣ|人~rén/人们~rénmen|人々~hitobito/人~hito|사람들~saramdeul/사람~saram|watu',
    ('child','singular'): 'child|niño|enfant|Kind|bambino|criança|طفل~ṭifl|孩子~háizi|子ども~kodomo|아이~ai|mtoto',
    ('child','plural'): 'children|niños|enfants|Kinder|bambini|crianças|أطفال~aṭfāl|孩子们~háizimen/孩子~háizi|子どもたち~kodomotachi/子ども~kodomo|아이들~aideul/아이~ai|watoto',
    ('mother','singular'): 'mother|madre|mère|Mutter|madre|mãe|أم~umm|母亲~mǔqīn|母親~hahaoya|어머니~eomeoni|mama',
    ('father','singular'): 'father|padre|père|Vater|padre|pai|أب~ab|父亲~fùqīn|父親~chichioya|아버지~abeoji|baba',
    ('family','collective'): 'family|familia|famille|Familie|famiglia|família|عائلة~ʿāʾila|家庭~jiātíng|家族~kazoku|가족~gajok|familia',
    ('name','singular'): 'name|nombre|nom|Name|nome|nome|اسم~ism|名字~míngzi|名前~namae|이름~ireum|jina',
    ('name','plural'): 'names|nombres|noms|Namen|nomi|nomes|أسماء~asmāʾ|名字~míngzi|名前~namae|이름들~ireumdeul/이름~ireum|majina',
    ('idea','singular'): 'idea|idea|idée|Idee|idea|ideia|فكرة~fikra|想法~xiǎngfǎ|アイデア~aidea|아이디어~aidieo|wazo',
    ('idea','plural'): 'ideas|ideas|idées|Ideen|idee|ideias|أفكار~afkār|想法~xiǎngfǎ|アイデア~aidea|아이디어들~aidieodeul/아이디어~aidieo|mawazo',
    ('reason','singular'): 'reason|razón|raison|Grund|motivo|motivo|سبب~sabab|理由~lǐyóu/原因~yuányīn|理由~riyū|이유~iyu|sababu',
    ('reason','plural'): 'reasons|razones|raisons|Gründe|motivi|motivos|أسباب~asbāb|理由~lǐyóu/原因~yuányīn|理由~riyū|이유들~iyudeul/이유~iyu|sababu',
    ('example','singular'): 'example|ejemplo|exemple|Beispiel|esempio|exemplo|مثال~mithāl|例子~lìzi|例~rei|예시~yesi|mfano',
    ('example','plural'): 'examples|ejemplos|exemples|Beispiele|esempi|exemplos|أمثلة~amthila|例子~lìzi|例~rei|예시들~yesideul/예시~yesi|mifano',
    ('world','singular'): 'world|mundo|monde|Welt|mondo|mundo|عالم~ʿālam|世界~shìjiè|世界~sekai|세계~segye|dunia',
    ('story','singular'): 'story|historia|histoire|Geschichte|storia|história|قصة~qiṣṣa|故事~gùshi|物語~monogatari|이야기~iyagi|hadithi',
    ('story','plural'): 'stories|historias|histoires|Geschichten|storie|histórias|قصص~qiṣaṣ|故事~gùshi|物語~monogatari|이야기들~iyagideul/이야기~iyagi|hadithi',
}


def forms(cell, language):
    values = []
    for value in cell.split('/'):
        parts = value.split('~')
        if len(parts) not in (1,2): raise ValueError('One optional reading')
        native = parts[0]
        reading = readable_roman(parts[1]) if len(parts) == 2 else ''
        if language in ('ar','zh','ja','ko') and not reading:
            raise ValueError('Every non-Roman form needs its own Latin reading')
        if not native or native.strip() != native: raise ValueError('Invalid written form')
        values.extend((variant, reading) for variant in form_variants(native, language))
    if len(values) != len(set(values)): raise ValueError('Duplicate explicit form')
    return values


def permitted_source(topic, number, language):
    # Complete counterpart presence cannot resolve a negative pronoun or an
    # Arabic conjunction/scholar when another clause supplies the target noun.
    # Keep these available as targets; positive source contexts need a later,
    # separately assessed frame rather than a context-free permission.
    return not ((topic == 'person' and number == 'singular' and language == 'fr') or
                (language == 'ar' and topic in ('mother', 'world')))


def records():
    for (topic, number), line in DATA.items():
        parsed = {lang: forms(cell,lang) for lang,cell in zip(LANGUAGES,line.split('|'),strict=True)}
        for source,lefts in parsed.items():
            if not permitted_source(topic, number, source): continue
            for target,rights in parsed.items():
                if source == target: continue
                for li,(left,_) in enumerate(lefts):
                    for ri,(right,reading) in enumerate(rights):
                        row = mapping('people_ideas_'+topic+'_'+number,source,target,left,right,left,right,MEANINGS[topic],reading)
                        row['logical_id'] += ':'+str(li)+':'+str(ri)
                        row['usage'].update(context_extent='local_phrase',lexical_unit=True,whole_reference=False,
                            context_generalization='explicitly assessed complete noun; only the listed number-group counterpart is allowed',
                            number_group=number,
                            source_frame_span=row['source_span'][:],target_frame_span=row['target_span'][:],
                            source_frame_pattern=[{'focus':left}],target_frame_pattern=[{'focus':right}],
                            permitted_context=MEANINGS[topic]+'; both complete unique native forms must occur in the actual local translation',
                            abstain_when=['Either complete counterpart is absent or occurs more than once.',
                                'Conflicting meanings/readings, protected literals or invalid native boundaries prevent alignment.',
                                'Unlisted possessors, articles, inflections and contractions receive no inferred mapping.'])
                        row['provenance'].update(priority_basis='Common people and ideas vocabulary; AfriSenti training-only priorities include watu and mtu. No evaluation utterance supplied authoring.',
                            form_source='Project-authored explicit forms, not an automatic dictionary import',
                            number_scope='Singular and plural meanings are separate; listed collective words such as gente denote people despite singular grammatical agreement. Some native nouns leave number unmarked.',
                            whole_reference_eligibility='False: a lexical carrier is not a sentence translation')
                        validate(row); yield row


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records())
    assert len({r['logical_id'] for r in rows}) == len(rows)
    args.output.mkdir(parents=True,exist_ok=False)
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical({'records':len(rows),'topics':len(MEANINGS),'number_groups':len(DATA),
        'pairs':len({(r['source_language'],r['target_language']) for r in rows}),
        'records_sha256':digest_file(path),'authoring_source_sha256':digest_file(Path(__file__)),
        'author_assessment_pending':True,'release_ready':False}))
