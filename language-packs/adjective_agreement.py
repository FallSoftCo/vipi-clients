"""Whole, attested Romance adjective agreement forms.

Agreement changes grammatical gender/number, not the adjective's degree or
lexical meaning. The actual translated form is still selected from the local
whole-message translation. No stem or new spelling is generated here.
"""
LANGUAGES = frozenset({"es", "fr", "it", "pt"})
ALLOWED = frozenset({"form-of", "feminine", "masculine", "singular", "plural"})
AGREEMENT = frozenset({"feminine", "masculine", "plural"})

def whole_form(head, form, pos, tags, language):
    tags = set(tags)
    if language not in LANGUAGES or pos != "adj" or head == form:
        return None
    if not tags or not tags <= ALLOWED or not tags & AGREEMENT:
        return None
    if not head.isalpha() or not form.isalpha():
        return None
    # Adjective agreement is not referential noun number. Existing degree,
    # sense, source-analysis, phrase and target-reading checks remain in force.
    return 0, len(form.encode("utf-16-le")) // 2, 0, 2
