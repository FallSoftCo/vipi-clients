# Concept corroboration diagnostic — 2026-10-28

The existing pinned Cygnet 2026.05.12 source was checked against retained
English→Spanish dictionary-linked gaps. No new source was downloaded, no
concept was merged with a Wiktionary sense, and no runtime rule or language
pack was changed.

analyze_cygnet_correspondences.py retains every known Cygnet concept/POS for a
written form, uses exact NFC/lower keys rather than the source's accent-stripped
key, and reports only cases where the target covers all those source concepts.
It also requires an existing dictionary-linked candidate from the earlier
diagnostic. The source remains incomplete and its forms are not automatically
valid inflections.

The 2.21-second run found 50 possible pairs in 40 of the 200 retained SMS
messages, including 20 empty messages in the older 80/200-message baseline.
These counts are candidate leads, not additional app coverage; some overlap
later gains. They include expensive→caro, objection→objeción, hamster→hámster
and already→ya. Case, grammatical role, whole-word geometry, idioms, duplicate
occurrences and pronunciation remain unqualified.

A concrete counterexample prevents promoting this generic containment rule:
Cygnet concept 70661 denotes a written meeting record, yet its Spanish forms
include minutos. The correct Spanish term for meeting minutes is actas;
minutos refers to time units. The retained SMS time-unit minutes→minutos
candidate happens to be a valid translation, but this concept would supply the
wrong semantic evidence for it. Merely sharing a spelling cannot establish
equivalence between this concept and a native dictionary sense.

artifacts/cygnet-corroboration-sms-001/meeting-minutes-counterexample.json
retains the exact source rows and contributing-resource identities. The
candidate and receipt files retain source hashes, per-resource license metadata
and explicit non-acceptance flags. This is an author finding, not independent
evaluation. The source contains no Swahili language entry, so it cannot by
itself close our namesake-language gap.

Useful next work is to connect reviewed meanings to the native dictionary
senses with explicit provenance, retain unmatched/contrary senses, and qualify
actual native output. Word counts, shared concepts or a larger index alone do
not establish the requested conversational immersion standard.
