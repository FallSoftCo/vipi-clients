"""Resolve only explicit dictionary lemma relations, never inferred stems.

Exact source line IDs preserve etymologies. Cycles, conflicting references,
mixed lexical/form entries and unresolved homographs keep their own identity.
"""
from functools import lru_cache
import json
import re
from build_wiktextract import EXCLUDED, PARTS, DIALECTS
from context_hints import lookup_key
from swahili_lexical import derived_entry,supplied_infinitive,derivation_definition


class NativeLinks:
    def __init__(self, db, language, redirects):
        self.db=db;self.language=language;self.redirects=redirects
        self.resolved={};self.evidence={}

    @lru_cache(maxsize=250000)
    def entry(self, identifier):
        return self.db.execute('''SELECT source_line,headword,normalized,part_of_speech,tags,source_url
            FROM native_entries WHERE source_line=?''',(identifier,)).fetchone()

    @lru_cache(maxsize=250000)
    def senses(self, identifier):
        return tuple(self.db.execute('SELECT glosses,tags,form_of,alt_of FROM native_senses WHERE source_line=?',(identifier,)))

    @lru_cache(maxsize=150000)
    def candidates(self, word, pos=''):
        key=lookup_key(word,self.language)
        direct=list(self.db.execute('''SELECT source_line,headword,part_of_speech FROM native_entries
            WHERE language=? AND normalized=?''',(self.language,key)))
        exact=[r for r in direct if r[1]==word]
        if exact:direct=exact
        result={i for i,h,p in direct if not pos or pos==p}
        # A hyphenated root or alternate script is accepted only when the
        # canonical entry explicitly supplies that exact spelling.
        infinitives=set()
        for identifier,head,p,tags,written in self.db.execute('''SELECT e.source_line,e.headword,e.part_of_speech,f.tags,f.form
            FROM native_forms f JOIN native_entries e USING(source_line)
            WHERE f.normalized=? AND e.language=?''',(key,self.language)):
            tags=set(json.loads(tags))
            if (not pos or pos==p) and not tags&EXCLUDED and tags&{'canonical','alternative'}:
                result.add(identifier)
            if (not pos or pos==p) and written==word and supplied_infinitive(self.language,head,p,written,tags):
                infinitives.add(identifier)
        if len(infinitives)==1:result.update(infinitives)
        return tuple(sorted(result))

    def resolve(self, identifier, trail=()):
        if identifier in self.resolved:return self.resolved[identifier]
        if identifier in trail or len(trail)>12:return identifier
        entry=self.entry(identifier);_,head,key,pos,tags,url=entry
        refs=set();features=set();lexical=False;invalid=False
        for glosses,raw_tags,form_of,alt_of in self.senses(identifier):
            tags=set(json.loads(raw_tags))
            if tags&EXCLUDED:continue
            forms=json.loads(form_of);alts=json.loads(alt_of)
            if derived_entry(self.language,pos,tags):
                # Causative, applicative, reciprocal and stative verbs retain
                # their own meanings: lend must never collapse into borrow.
                lexical=True;continue
            if forms or alts:
                refs.update(r['word'] for r in forms+alts);features.update(tags)
                # A qualified alias can narrow meaning; it is not an identity.
                if any(r.get('extra') for r in forms+alts):invalid=True
            elif tags&{'form-of','alt-of'}:invalid=True
            elif json.loads(glosses):lexical=True
        redirects=self.redirects.get(identifier,())
        if redirects:refs.update(redirects)
        result=identifier
        if refs and not lexical and not invalid:
            choices=set()
            for ref in sorted(refs):
                candidates=self.candidates(ref,'' if redirects else pos)
                if redirects:
                    # A multi-POS kana redirect is disambiguated only by an
                    # explicit alternate-form backlink to this written head.
                    linked=set(self.candidates(head))-{identifier}
                    backed=[c for c in candidates if c in linked]
                    if backed:candidates=tuple(backed)
                roots={self.resolve(c,trail+(identifier,)) for c in candidates if c!=identifier}
                if not roots:invalid=True;break
                choices.update(roots)
            if not invalid and len(choices)==1:
                candidate=next(iter(choices))
                if candidate not in trail and candidate!=identifier:result=candidate
        self.resolved[identifier]=result
        if result!=identifier:self.evidence[identifier]=(result,sorted(refs),sorted(features),'redirect' if redirects else 'native-form-or-alternative')
        return result

    def derived_counterpart(self, identifier, english, label):
        """A derived verb must have its own matching published definition."""
        if self.language!="sw" or self.entry(identifier)[3]!="verb":return None
        found=False;matches=False
        normalize=lambda value:re.sub(r"^to ", "", value.strip().lower().rstrip("."))
        for raw,tags,forms,alts in self.senses(identifier):
            tags=set(json.loads(tags))
            if tags&EXCLUDED:continue
            if not derived_entry(self.language,"verb",tags):continue
            found=True
            definition=derivation_definition(self.language,"verb",json.loads(raw),tags,json.loads(forms),json.loads(alts))
            if not definition:continue
            value=normalize(definition);word=normalize(english);sense=normalize(label)
            if value==sense or word in {normalize(part) for part in re.split("[,;]",definition)}:
                matches=True
            if value==word+" ("+sense+")":matches=True
        return matches if found else None

    def chinese_character_counterpart(self, identifier, english):
        """Corroborate an existing English translation with an explicit gloss.

        Wiktionary labels Chinese one-character lexical words "character",
        including eat, book and rice. Do not invent a POS or a translation:
        this is only used for a published bilingual link whose exact English
        counterpart also occurs as a complete, unqualified native gloss item.
        """
        if self.language!='zh' or self.entry(identifier)[3]!='character':return False
        allowed={'transitive','intransitive','ditransitive','countable','uncountable',
            'Mandarin','Standard-Chinese'}
        for raw,tags,forms,alts in self.senses(identifier):
            tags=set(json.loads(tags))
            if tags&(EXCLUDED|DIALECTS) or tags-allowed or json.loads(forms) or json.loads(alts):continue
            glosses=json.loads(raw)
            if not glosses:continue
            gloss=glosses[-1].strip().lower().rstrip('.')
            # Classifier lists are editorial noun metadata, not a restriction
            # on the English meaning. Remove only this exact trailing syntax.
            gloss=re.sub(r'\s*\(classifier: [^()]*\)$','',gloss,flags=re.IGNORECASE)
            words=[re.sub(r'^to ','',part.strip()) for part in re.split('[,;]',gloss)]
            if any(not re.fullmatch(r"[a-z]+(?:[ '-][a-z]+){0,3}",w) for w in words):continue
            if english.lower() in words:return True
        return False

    def simple_glosses(self, identifier):
        """A contradictory explicit short English gloss vetoes a guessed link.

        This is negative evidence, never an automatic sense certification.
        Descriptive definitions and mixed analyses are not reduced to keywords.
        """
        values=set()
        for raw,tags,forms,alts in self.senses(identifier):
            if set(json.loads(tags))&EXCLUDED:continue
            if json.loads(forms) or json.loads(alts):return set()
            glosses=json.loads(raw)
            if not glosses:return set()
            gloss=glosses[-1].lower().rstrip('.')
            gloss=re.sub(r'^to ','',gloss)
            pieces=[re.sub(r'^to ','',s.strip()) for s in re.split('[,;]',gloss)]
            if any(not re.fullmatch(r"[a-z]+(?:[ '-][a-z]+)?",s) for s in pieces):return set()
            values.update(pieces)
            # Definitional articles are editorial scaffolding: the native
            # gloss "an island, an isle" corroborates an existing island link.
            # Retain original strings and only add article-free noun items.
            # This cannot create bilingual links or certify a narrower sense.
            if self.entry(identifier)[3]=='noun':
                values.update(re.sub(r'^(?:a|an) ', '', item) for item in pieces)
        return values

    @lru_cache(maxsize=100000)
    def matching_sense_gloss(self, identifier, label):
        """An exact unqualified definition can corroborate a published sense.

        English doctor has several senses. A native medical-doctor definition
        matches only the published medical-doctor label, not every sense of
        doctor. Short definitions with mixed/qualified analyses do not qualify.
        """
        from build_native_gloss_links import counterparts
        parsed=counterparts(self.senses(identifier))
        return bool(parsed and parsed[0].strip().lower().rstrip('.')==label.strip().lower().rstrip('.'))

    @lru_cache(maxsize=100000)
    def matching_english_definition(self, english_identifier, word, pos):
        """Corroborate an existing translation, never create a new synonym link.

        A short native gloss can use a different English name for the same
        thing. Keep a published bilingual link when both English entries have
        one identical, substantive modern definition (e.g. railway/train
        station). This only prevents a false contradiction veto.
        """
        def leaf(identifier):
            values=set()
            for raw,tags,forms,alts in self.senses(identifier):
                if set(json.loads(tags)) & EXCLUDED:continue
                if json.loads(forms) or json.loads(alts):return None
                glosses=json.loads(raw)
                if not glosses:return None
                values.add(glosses[-1])
            value=next(iter(values)) if len(values)==1 else None
            return value if value and len(value)>=24 and len(value.split())>=5 else None
        definition=leaf(english_identifier)
        if not definition:return False
        for identifier,tags in self.db.execute('''SELECT source_line,tags FROM native_entries
            WHERE language='en' AND normalized=? AND headword=? AND part_of_speech=?''',(lookup_key(word,'en'),word,pos)):
            if not set(json.loads(tags)) & EXCLUDED and leaf(identifier)==definition:return True
        return False

    def close(self):
        self.entry.cache_clear();self.senses.cache_clear();self.candidates.cache_clear()
        self.matching_english_definition.cache_clear();self.matching_sense_gloss.cache_clear()
