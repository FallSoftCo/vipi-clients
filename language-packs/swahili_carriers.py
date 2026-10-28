"""Compose bounded Swahili carriers from supplied conjugations and object forms.

Only the unchanged lexical root is the focus. Every object stem and conjugated
base must occur in the same native entry's table. Reflexives, vowel-initial
roots, monosyllables and final-vowel changes are deliberately outside this rule.
No whole-message translation or transliteration is generated.
"""
from build_wiktextract import EXCLUDED

RULE = "supplied-swahili-object-concord-composition-1"
REFERENCES = ["https://en.wiktionary.org/wiki/Appendix:Swahili_verbs#Object_concords",
              "https://en.wiktionary.org/wiki/Appendix:Swahili_verbs#Infinitive"]
OBJECTS = {"ni", "ku", "m", "tu", "wa", "u", "i", "li", "ya", "ki", "vi", "zi", "pa", "mu"}
PERSON = {"first-person", "second-person", "third-person"}
TENSE = {"present", "past", "future", "perfect"}

def transitivity(senses):
    """Only an explicit modern transitive sense or explicitly defined causative."""
    import json
    from swahili_lexical import derivation_definition
    evidence = []
    for glosses, raw_tags, form_of, alt_of in senses:
        tags = set(json.loads(raw_tags))
        if tags & EXCLUDED:
            continue
        if "transitive" in tags and not tags & {"intransitive", "form-of", "alt-of"}:
            evidence.append(dict(kind="explicit-transitive", glosses=json.loads(glosses), tags=sorted(tags)))
        elif "causative" in tags:
            definition = derivation_definition("sw", "verb", json.loads(glosses), tags,
                json.loads(form_of), json.loads(alt_of))
            if definition:
                evidence.append(dict(kind="defined-causative", definition=definition, tags=sorted(tags)))
    return evidence

def records(head, pos, head_tags, forms, transitivity_evidence):
    if (not transitivity_evidence or pos != "verb" or set(head_tags) & EXCLUDED or not head.isascii()
        or not head.isalpha() or head != head.lower() or head[0] in "aeiou"
        or sum(c in "aeiou" for c in head) < 2):
        return
    objects = []
    bases = []
    for written, raw_tags in forms:
        tags = set(raw_tags)
        if tags & (EXCLUDED | {"reflexive", "relative", "error", "table-tags", "subjunctive", "imperative"}):
            continue
        if {"object-concord", "indicative"} <= tags and written.startswith("-") and written.endswith(head):
            prefix = written[1:-len(head)]
            if prefix in OBJECTS:
                objects.append((prefix, written, sorted(tags)))
        elif ("object-concord" not in tags and written.isascii() and written.isalpha()
              and written == written.lower() and written.endswith(head) and written != head
              and (tags == {"infinitive"} or (tags & PERSON and tags & TENSE))):
            prefix = written[:-len(head)]
            # This class never needs an extra stress-supporting ku-.
            if prefix.endswith("ku") and tags != {"infinitive"}:
                continue
            bases.append((prefix, written, sorted(tags)))
    for prefix, base, base_tags in bases:
        for concord, object_form, object_tags in objects:
            written = prefix + concord + head
            start = len(prefix) + len(concord)
            evidence = dict(supplied_base=base, supplied_base_tags=base_tags,
                supplied_object=object_form, supplied_object_tags=object_tags,
                head=head, transitivity=transitivity_evidence, references=REFERENCES)
            features = sorted(set(base_tags) | {RULE, "object-concord", "object-prefix:" + concord})
            yield (written, start, len(written), 0, features), evidence
