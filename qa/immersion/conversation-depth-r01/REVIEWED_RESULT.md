# Ordinary conversation exposes a depth gap

The current lookup route still needs substantially broader useful content. The
80-message diagnostic at source revision `1d42f9c` reaches 63 messages in Japanese
and 68 in Swahili, but many matches are only pronouns, conjunctions or degree
words. Increasing density from 0.25 to 0.75 adds words inside already matched
messages; it reaches no additional message in this sample.

The normal native factories ran with translation-model availability explicitly
unavailable to isolate lookup. These results do **not** measure the installed
local-translation fallback or the complete product with prepared models. Both
platforms agree on all 320 outputs, readings and source geometry, with zero
translation calls. All selected units are starter words: the 41 finite-context
patterns and exact sentence references contribute no selected unit on these
inputs. Their earlier bounded qualification does not establish generalization
to everyday dialogue.

Each reviewer inspected all 189 distinct complete outputs with relevant prior
dialogue and Japanese readings. Their labels and useful-content definitions
remain separate. At density 0.75:

| Measure, denominator 80 messages per pair | Japanese | Swahili |
|---|---:|---:|
| Any displayed span | 63 | 68 |
| Strict useful messages, root reviewer | 39 | 41 |
| Strict useful messages, independent reviewer | 31 | 35 |
| Minor-inclusive useful messages, root reviewer | 44 | 45 |
| Minor-inclusive useful messages, independent reviewer | 37 | 39 |
| Mean strict correct word depth, root reviewer | 15.49% | 18.37% |
| Mean strict correct word depth, independent reviewer | 15.22% | 18.68% |

Word depth includes zeros and compatible function words. Restricting it to
reviewed useful content gives only 4.7–6.2% Japanese and 5.5–6.8% Swahili, across
the two reviewers. Root credits some descriptive/degree modifiers which the
independent reviewer treats as function-only. Those definition differences are
retained rather than averaged into an accuracy claim.

The reviewers agree on the central limits: thin content, fixed-expression
fragments, opinion/discourse nuances, and uncertain animal-hair terminology.
The latter is the substantive correction: source dialogue identifies a cat,
whereas the retained Swahili entry establishes human-head hair. Root labeled it
material and the independent reviewer uncertain before checking the source.
The subsequent primary-source check supports withholding that mapping, without
inventing an animal translation or silently changing either frozen review.
See the separate `../contextual-sense-hold-r01` correction and qualification.
Other disagreements, including the Japanese year reading and Swahili “no idea,”
remain explicit concerns.

Selection used 40 persona and 40 empathetic-context conversations with fixed
length quotas, one free-worker message per conversation and hash ordering.
Exact/normalized source and complete-prior overlaps were excluded against the
declared retained inventory. Five cases include an individually repeated prior
turn. This is prompted crowdsourced dialogue, not a population sample, unseen
model-training data or native-human gold. Prior dialogue was reviewer-only;
runtime inputs contained only the selected message. The sample is now exposed
development evidence and must not be reused as untouched acceptance data.

The next content work should target common predicates and conversational
constructions. Existing reviewed Swahili predicate surfaces occur in 20/80
messages before sense/budget guards, but that count is only an opportunity
inventory, not permission or predicted improvement. The unchanged remainder of
the corpus remains available for later confirmation. Broad coverage, durable
familiarity and other language directions remain open.

`completion-r01.json` retains capture/cleanup evidence, including Android's
abnormal post-capture shutdown. `reviewed-scorecard-r01.json` retains both
reviewers, all strata, disagreements and exact evidence hashes. No store,
provider, signing or iPad action occurred.
