The largest first-loss group is **not predominantly made of utterances outside the experiment’s POS scope**. Of the 3,190 expanded-arm messages with no eligible dictionary link, 2,971 (93.1%) contain at least one exact native word tagged NOUN, ADJ or ADV. They contain 8,911 such word occurrences, with no projected head focus. This establishes missing pipeline support for potentially in-scope words, not missing meanings or recoverable correct translations.

| In-scope native words in the 3,190-message group | Messages | Any projected focus |
|---|---:|---:|
| Zero | 219 | 0 |
| One | 663 | 0 |
| Two or more | 2,308 | 0 |

Within the 219 zero-scope messages, 167 contain a VERB token, 31 contain AUX but no VERB, and 21 contain neither. Thus 198 meet the requested **verb/auxiliary-present, no-in-scope-word proxy**. They can still contain function words, proper names or unmapped tokens; “verb-only” would not mean every word is a verb. The remaining 2,971 messages cannot be dismissed as intentionally excluded verb-only utterances.

For comparison, across all 9,535 messages, only 301 have zero in-scope words; 997 have one and 8,237 have two or more. The principal expanded-arm first-loss groups cross as follows, before family exhaustion. These are the same ordered availability classes as r01, reproduced exactly.

| First-loss class | Total | Zero in-scope | One | Two or more | Any projected focus |
|---|---:|---:|---:|---:|---:|
| No eligible link | 3,190 | 219 | 663 | 2,308 | 0 |
| No structurally eligible head | 599 | 5 | 46 | 548 | 0 |
| Actual role unassessed | 282 | 12 | 34 | 236 | 282 |
| No shared-head context | 93 | 44 | 33 | 16 | 0 |
| No retained source context | 29 | 21 | 6 | 2 | 0 |
| No aligned context | 2 | 0 | 1 | 1 | 0 |

All 282 role-unassessed cases have some projected focus, but none on an exact native in-scope word; 270 nevertheless contain in-scope words elsewhere. This distinguishes a candidate attached to an out-of-scope/unassessed focus from an utterance with no in-scope vocabulary at all. Under the additional 300-family withholding state, all 1,681 newly withheld messages have in-scope words and projected in-scope focuses: that loss is the explicit withholding policy.

The next diagnostic remains the complete supported head-to-target evidence gap. The crossing rules out whole-utterance POS exclusion as its main explanation, but does not separate absent source forms, absent retained sense links, unsafe/incomplete target forms, or the wrong frozen corpus witness. Existing tags can also be wrong. None of these counts authorizes lifting explicitness, target-safety, alignment or compound guards, and adding verbs remains a separate scope question.

The single read-only pass completed in **15.98 seconds**, with **60,309,504 bytes VmHWM** and **33,500 bytes of aggregate output**. It verified every r01 first-loss count for both arms and both states, retained exact input hashes, and wrote separate immutable r02 evidence. No raw samples, selector replay, new annotation, proof copy, cleanup or guard change occurred. [Receipt](loss-accounting-r02-receipt.json); [complete scope/focus crossings](/home/ai/Development/investigations/vipi-context-key-expansion-20261109-r01/head-preparation-r01/loss-accounting-r02/result.json). r01 artifacts remain unchanged.
