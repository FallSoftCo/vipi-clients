# Immersion coverage acceptance

The working coverage floor is 90% in **each of the 110 supported directions**.
This is a product target, not an achieved result. Counting a message because one
word changed is only an availability diagnostic: it does not prove useful
immersion, correct meaning, or a learning outcome.

## Fixed denominators

The scorecard retains every message in each named diagnostic dataset, including
identifier-preservation failures, messages with no native word tokens and
abstentions. Any future eligibility rule must be declared before evaluation,
depend only on the source message, and report both the original denominator and
excluded messages. Never remove a case because the selector cannot handle it.

SMS, task dialogue, persona dialogue and Swahili speech-derived turns stay
separate. The latter includes fragments and code-switching; it is not a general
Swahili text-chat estimate. Reused translations are marked as such. FLORES
reference sentences are a separate diagnostic, never a replacement for missing
conversational evidence. Repeated translations of one source are not independent
conversations.

The current conversational diagnostics cover 73 directions. The other 37 remain
unmeasured: all ten directions from Spanish, German and Portuguese, plus
English/French/Italian/Arabic/Chinese/Japanese/Korean into Swahili. Reference
diagnostics exist for all 110. Passing authored dictionary probes does not close
these sampling gaps.

## Availability, depth and meaning

qa/immersion/coverage_scorecard.py validates the immutable native replay against
its exact fixture before reporting anything. It emits every direction, explicitly
marks missing samples, and checks the 90% availability floor separately within
each sampled dataset. There is no pooled pass that can hide a weak direction.

Both native QA implementations now record their own UTF-16 word ranges. The
scorecard reports the proportion of source words touched by selected immersion
spans and the proportion fully covered. These differ for a lexical stem inside
an inflected carrier. It reports message distributions and proportions reaching
10%, 25% and 50% depth, retaining zero-coverage messages. Older reports without
native boundaries have unknown depth, not an estimated passing score.

These runs select at density=1 to measure available material. They do not prove
the live progression can achieve a user's selected density. The three reported
depth levels are diagnostics, not newly selected product settings or acceptance
thresholds. Useful-immersion acceptance remains false until sufficient depth is
established alongside availability.

The proposed meaning-accuracy target is at least 99% on independently reviewed,
contextual substitutions. Existing author-reviewed regressions do not establish
that percentage. Track serious meaning changes separately, including negation,
numbers, people, names, time, idioms and false sense alignment. A whole-sentence
translation can be wrong even when its vocabulary is aligned consistently; those
errors cannot disappear from evaluation.

Use the same meaning and depth checks for non-Roman targets, with required
transliteration and correct audio. Coverage is not evidence that users reach
intermediate fluency; learning outcomes require their own evaluation.

## Continuous expansion

Keep development examples, authored regressions and reserved acceptance data
separate. Preserve all existing exclusion indexes when adding mining sources,
including the full FLORES development and test identities. Inspecting or fixing
a diagnostic example does not turn it into untouched acceptance evidence.

Expand from frequent missed conversational vocabulary, inflections, phrases and
context distinctions. Rebuild using both supporting and contradicting evidence,
then replay both native platforms. Review every newly selected mapping in a
bounded selector change before accepting the change. Dictionary size, rule count,
FTS hits and corpus agreement percentages are not substitutes for coverage or
semantic accuracy.

OpenAssistant OASST1 is a possible additional multilingual prompt diagnostic
(https://huggingface.co/datasets/OpenAssistant/oasst1). Its Apache-2.0 dataset card
describes assistant conversations with message-tree, language, role and synthetic
fields. It has not been acquired or mined for this revision. Assistant prompts
must remain separately labeled and cannot establish ordinary friend-chat
coverage merely by filling a language column.

