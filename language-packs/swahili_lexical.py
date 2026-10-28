"""Interpret supplied Swahili lexical derivations without equating their meanings."""
DERIVATIONS={"causative":"Causative","applicative":"Applicative","stative":"Stative","reciprocal":"Reciprocal"}

def derived_entry(language,pos,tags):
    return language=="sw" and pos=="verb" and bool(set(tags)&DERIVATIONS.keys())

def derivation_definition(language,pos,glosses,tags,forms,alternatives):
    """Only an exact source definition of this derived verb, not its base."""
    tags=set(tags);kinds=tags&DERIVATIONS.keys()
    if not derived_entry(language,pos,tags) or len(kinds)!=1:return None
    kind=next(iter(kinds))
    if tags!={"form-of",kind} or alternatives or len(forms)!=1 or not glosses:return None
    reference=forms[0];word=reference.get("word","");extra=reference.get("extra","")
    if not word or not isinstance(extra,str) or not extra.startswith("to ") or len(extra)<=3:return None
    if glosses[-1]!=DERIVATIONS[kind]+" form of "+word+": "+extra:return None
    return extra

def supplied_infinitive(language,head,pos,written,tags):
    """Require the exact native table form; this never synthesizes a word."""
    return (language=="sw" and pos=="verb" and set(tags)=={"infinitive"}
        and head.isascii() and head.isalpha() and head==head.lower()
        and written.isascii() and written.isalpha() and written==written.lower()
        and written.endswith(head) and written[:-len(head)] in {"ku","kw"})
