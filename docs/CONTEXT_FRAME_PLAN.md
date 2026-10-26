# Context phrase qualification

Status: implementation plan, not implemented or linguistically accepted.

The dictionary path recognizes words in most diagnostic messages but frequently cannot establish their intended sense. Adding 353 observed plural forms did not increase strict Android message availability. Exact reviewed sentences perform much better, but arbitrary real messages rarely match a whole authored sentence.

The next experiment generalizes **explicitly assessed local phrases**, such as the reading construction around a book, rather than treating a similar search result as meaning approval. Each record retains a lexical focus and finite literal/slot alternatives. Both the original message and its actual local translation must contain an accepted phrase for the same record. Pronouns, negation, possession, identifiers and surrounding grammar remain outside the displayed focus.

## Implementation sequence

1. Introduce a distinct record extent, pack policy and schema for source/target phrase contexts. Existing exact-sentence packs retain their current meaning. Require an assessment explicitly covering the phrase's permitted surroundings; do not migrate prior author assessments automatically.
2. Compile finite source and target phrase variants into indexed SQLite tables linked by mapping ID, preserving full attribution and assessments. Bound record size, variants and query results; overflow abstains rather than truncating competing claims.
3. On each native platform, enumerate bounded contiguous native-word windows inside sentence boundaries and look up exact phrases. Keep offsets in the original strings. No arbitrary stemming, nearest-neighbour acceptance or target interpolation.
4. Require the same mapping to match a source phrase and target phrase. Reject conflicting records or ambiguous occurrences. Produce ephemeral source **and target** scopes bound to the exact messages; generic vocabulary deserialization cannot grant either scope.
5. Feed those scopes into existing protected-text, reading, ambiguity, stable display and speech behavior. Original messages remain readable if a phrase is unavailable or uncertain. Do not weaken the current generic dictionary path merely to increase counts.
6. Author a small first set of common constructions across ten languages and all 90 directions. Keep author assessment distinct from independent acceptance. Include number/person changes outside focus, prepositions, negation, unrelated senses, compounds/names, repeated targets and non-Roman readings.
7. Capture actual Apple/ML Kit translations of authored phrase contexts and longer messages. Assembled translations are mechanical tests only. Run native pack/offset/ambiguity tests, inspect selected substitutions, then evaluate on fresh, clearly identified real-message material after development regressions pass.

## Limits to resolve

Surrounding text can change a phrase's meaning. An author must state why the permitted frame supplies sufficient context and when to abstain. Provider translation may omit or change the frame. Native tokenization can split compounds or attach particles. Source/target occurrences cannot be paired solely by position or frequency. A broad context rule needs evidence beyond a successful exact example.

This approach must demonstrate useful coverage before broader rollout. The target remains relevant, seamless immersion through ordinary conversation; no lesson flow, remote immersion model or new user interaction is introduced.
