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
