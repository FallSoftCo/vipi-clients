# Source-unit integration contract, revision 3

This contract supports native qualification. The research catalog is not a
production allowlist. No inference, data activation, or learned-word persistence
is authorized merely by implementing the interface.

## Inputs and identity

The frozen research candidate is
`editorial-runtime-candidate-r03.json`, SHA-256
`38a5c9989baa7603d5caf2bb03c2ca38021b56e0cba871a1b4b16e4de98aedc1`.
It contains 1,139 editorial mappings, 463 source/POS pairs, and complete-form
source-role metadata for 6,384 forms. Targets are Swahili, Japanese and Spanish;
the source is English. The old word producer input remains
`content-expansion-candidate-r01.json`, SHA-256
`5264106ac021932f97350767a792a53e74cdac2fed4242997c9e771a683508a4`.
These are two immutable research inputs, not a claim that every face is ready
for default activation. Full evidence and target readings must survive export.

Each supplied candidate has an exact original substring and UTF-16 range,
target face, target reading where mandatory, stable lexicon ID, concept ID,
content/function category, frozen TRAIN rank and proof identity. The proof
binds the exact catalog/version and entry. `concept_id` is shared across the
three English-source target packs and attested source inflections. It is not
yet a universal interlingual identifier for all 110 directions.

The lookup context carries source/target languages, density, message identity,
and an immutable set of known concept IDs. Cache identity includes the source
policy/catalog identity and that known-ID snapshot. A changed snapshot must
invalidate or segregate old partials. Receiving a message does not imply that
the user has learned its words.

## Hierarchy and admission

1. Existing accepted whole references and accepted sentence-unit lookup remain
   first. A useful approved partial may terminate automatic immersion before
   model readiness or translation. Explicit full translation remains separate.
2. The additional word producer combines old reviewed-word candidates with
   editorial candidates, preserving the old face for the same occurrence and
   concept. The producer does not replace an earlier accepted sentence result.
3. Apply original-source URL/code/quote protection to **every** candidate path,
   including function words, before ranking. The research parser recognizes
   balanced double/curly quotes and backticks; an unmatched opener protects to
   the end. Arbitrary escaped/nested syntax is not claimed qualified.
4. Apply the original entry-specific guard and the shared source-role guard.
   Source role metadata is independent of whether that word has a target face.
   Preserve the frozen 508-source noun-only proxy; do not broaden it implicitly.
   Membership in a possible noun or adjective class is not actual contextual
   POS. The separate following-any-noun attributive suppression arm is rejected.
5. A native whole-source token basis must validate every proposed scope. Never
   trim inflected words or infer range permission from a Python token count.
   Native identifier/literal, reading and presentation validation still apply.

## Selection

Remove known concept IDs before selection. Sort by content before function,
then ascending frozen TRAIN rank, descending complete native source-token cost,
ascending source UTF-16 start and lexicon ID. Choose source-disjoint units,
at most one occurrence per concept per message, up to 128 selected units.

The budget is `max(1, floor(nativeSourceWordCount * requestedDensity))`. Both an
individual unit and the total must fit it. No whole-unit budget override. The
same one-unit result does not establish 25% or 50% immersion depth. A completely
changed short message is legitimate if its approved complete unit fits, but is
reported separately from mixed text.

## Output and failure behavior

Return the existing partial presentation type with anchored source and local
reference/target ranges. Use the existing stable-slot rendering, readings and
original/mixed speech. Do not invent a complete sentence translation from
independent units. A lookup miss leaves the existing local-translation fallback
available; an explicit whole-translation request preserves the partial face,
phase and request identity while bounded/coalesced work runs.

The native provider/selector can be integrated with no production catalog by
default. Enabling real data requires a separate explicit approval manifest that
binds catalog hash, entry IDs and source-context conditions. The approval must
describe ordinary sense evidence and scope, not automatically exclude a word
because it was never selected in one small review.

## Evidence and outstanding limits

The R03 core changed-scope review found 24/24 jointly meaning-compatible
selected scopes, with a technical phrase caveat. It does not approve all 1,139
faces. Known whole-output errors include country music, raise the bar and high
school. Japanese counter readings versus isolated dictionary readings remain
an explicit contextual issue. Five Swahili forms carry upstream parser-warning
tags and must not be described as independently certified morphology.

All 9,535 comparison messages are reused BST TRAIN role-play diagnostics. The
word producer is not the current native production baseline. Native route
availability, word boundaries, steady cost and actual selected meanings require
their own exact-input comparison. The next separate experiment assesses typed
phrase slots and morphology; this contract does not claim those are implemented.
