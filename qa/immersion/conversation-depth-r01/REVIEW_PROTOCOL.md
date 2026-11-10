# Current conversation depth diagnostic

Freeze the sample and native outputs before semantic review. The sample has 80
distinct conversations, split equally between persona and empathetic contexts,
with fixed source-length quotas. It is a diagnostic sample of prompted human
dialogue, not a random sample of customer traffic. The exposure audit covers its
declared retained artifact inventory; it cannot prove absence from every prior
agent view or model training corpus.

Run the current default English→Japanese and English→Swahili routes at densities
0.25 and 0.75 with empty exclusions. Do not inject providers, translated targets
or spans. Retain every message, including empty results and errors. No new
source permissions or content changes belong to this diagnostic. Prior dialogue
is reviewer context only, physically separate from native inputs.

Review each distinct complete mixed output once, retaining the states which
produced it. Review the Japanese script and its displayed reading together.
Use the prior dialogue when necessary to assess intended meaning, and record
uncertainty instead of inventing context. Neither reviewer sees the other's
labels before finalizing their own. These are agent judgments, not native-human
gold labels.

Complete-output labels:

- **Compatible:** emitted faces retain the intended local meaning; deliberately
  mixed source grammar is not itself an error.
- **Minor:** meaning is retained but a face has a register, number, wording or
  reading concern worth correcting.
- **Material:** at least one emitted face teaches a substantially wrong sense,
  referent or relationship in this context.
- **Uncertain:** the available dialogue or reviewer's language confidence cannot
  resolve an emitted face safely.
- **Empty:** no immersion span was displayed. Do not count unchanged text as a
  correct immersion output.

Also identify useful content/construction spans in each complete output. Count
meaning-bearing nouns, predicates, descriptive words, and coherent multiword
expressions. Report pronoun/function-only messages separately; those can help
beginners but do not establish useful conversational depth. Record per-span
concerns so an otherwise correct phrase cannot conceal a wrong adjacent word.
Do not infer mastery, durable familiarity or learning effectiveness.

For each pair, density and dialogue stratum, report the unchanged message
denominator, nonempty messages, compatible messages with useful content,
minor-inclusive useful messages, material/uncertain outcomes, and native-word
depth including zeros. Strict correct depth credits only compatible complete
outputs; a separate minor-inclusive value may be shown. Report distinct
concepts and multiword focuses without treating aliases, context variants or
repeated density states as independent vocabulary or observations.

Verify output reconstruction, exact source spans, selected provenance and
translation-call counts independently of native selection. Platform parity is
an implementation observation, not semantic approval. Missing capture rows are
failures, not permission to shrink the denominator. Once outputs are inspected,
this sample becomes exposed development evidence; retain the unused remainder
for later confirmation of any proposed expansion.
