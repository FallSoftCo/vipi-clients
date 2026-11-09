# Completed execution

See [RESULT.md](RESULT.md) and `completion-receipt-r02.json` for the completed annotation/join, measured resource amendment, exact legacy parity and availability counts. The preparation record below is retained as historical planning.

# Frozen Apertium corpus-evidence preparation

The exact larger cohort contains **14,004 distinct full endpoints**: 6,968 English and 7,036 Spanish, comprising 131,705 supplied tokens and 600,127 UTF8 text bytes. These belong to 7,115 retained parallel pairs / 6,437 components and 7,701 distinct source-focus occurrences. The census reproduces all 1,480 heads, 1,470 context keys, 3,651 variants, 12,485 observations and 12,500 head-observation joins, including equality for every variant's retained observation count. Maximum endpoint length is 60 tokens / 346 UTF8 bytes.

The count-only pass took 3.706 seconds and 63,864,832 bytes VmHWM. The 7,986,748-byte endpoint identity/geometry manifest remains on production at `/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01/cohort/endpoint-inventory.json`, SHA256 `26a5f6fe70067d2d090d44393a502c17295de73a39d41691a89e9620daa1162d`. No larger annotation occurred. Small receipts are retained under `/home/ai/Development/investigations/vipi-apertium-corpus-evidence-20261109-r01`.

## Batching qualification

Reused all 64 frozen endpoints and existing raw stages. The retained `lt-proc` and `apertium-tagger` man pages document `-z` null flushing. The tagger uses `-g -p -z`; the analyzer uses `-z`. Each language was tested in original and reversed endpoint order, with 32 endpoints per batch. **All 256 endpoint/stage comparisons are byte-identical** to the original individual executions. This verifies contextual reset parity on the frozen cases, not universal linguistic correctness.

The initial strict record-count result remains false: the analyzer emits one extra empty EOF flush record, and the downstream tagger adds another. The additive audit verifies exactly the expected first 32 records and requires every extra split segment to be empty. No nonempty content is stripped, normalized or dropped. Original raw stdout, strict receipt and additive framing receipt remain immutable. The first batch script had a syntax error before execution; its bytes are archived as `qualify_batch.py.failed.txt`, with a private failure receipt. All active helpers have since passed AST syntax checking. No model invocation occurred in that failed attempt.

The existing `apertium-destxt` documented interface has no `-z`, so preprocessing remains one process per endpoint. No custom deformatter was introduced. Repeating this unchanged preprocessing for the 64 qualification endpoints took 0.307 seconds and reproduced every prior deformatter output byte-for-byte. This is separate from morphology/tagging, which were not replayed after the successful batch qualification.

## Proposed bounded larger run — not launched

Use batches of at most 32 endpoints per language, sorted by frozen endpoint key. Reconstruct from the retained exact pair manifest and verify every endpoint identity, text hash, token-geometry hash, source/target ID and component. Check every supplied token's codepoint and UTF16 substring, preserve parallel occurrence references, and deduplicate only identical endpoint/text/token identities. Existing 40k pair provenance and original source geometry remain authoritative.

Measured extrapolation is approximately 67.2 seconds for the unmodified per-endpoint deformatter plus 35.7 seconds for morphology/HMM batches, about **103 seconds**. This is an estimate, not a runtime guarantee. Proposed annotation ceiling: **one CPU, 256 MiB address space, 300 seconds total, 10 seconds per child, 32 MiB outputs**, preserving the 8 GiB free floor. Raw morphology plus contextual streams are estimated at roughly 8 MiB by token volume; retain them once with a compact endpoint offset/hash index. The two syntax/readiness failures from earlier tasks do not justify restarting completed inference.

Proposed evidence joining is a separate bounded stage: **one CPU, 1 GiB address space, 300 seconds, 96 MiB outputs**. Combined new output ceiling is 128 MiB, with 160 MiB additional reservation including metadata/scratch. The larger reservation uses the prior all-alternative audit scale rather than another tiny guessed cap. Count encoded record sizes before writing; fail with retained receipts if insufficient, without silently dropping alternative forms/readings. No full dictionary/proof copy, fitting, training, ranking, projection or activation is included.

## Exact focused-form joining

`form_role_join.py` is an evidence-only helper with four focused structural controls. For each retained head occurrence:

1. Preserve the existing context key, source displayed-focus coordinates, pair/endpoint provenance and all alignment-envelope reasons.
2. Enumerate complete supported dictionary noun forms at their actual source focus and within the target aligned envelope. Keep each form/unit/lexeme ID and every old guard/reason. A smaller target noun form remains distinct from an envelope containing an article or adjective; observing its role does not erase crossing, mutual-anchor or compound concerns.
3. Join each actual complete form's exact UTF16 scope to a single Apertium lexical-unit scope, preserving all morphological alternatives and contextual reading. Unknown, joined, ambiguous, split or nonexact multiword mappings remain unassessable. Do not demand that every token in the whole alignment envelope is NOUN. This is role evidence, not eligibility or correctness approval.
4. Keep old explicit shared links, old nonexplicit links and the 17 newly serialized direct-English unresolved candidate relations in separate strata. Preserve term eligibility, explicit flags, qualifiers, source/target form evidence and source-sense uncertainty. The new candidate relation must not inherit a fabricated source sense or authorize foreign-to-foreign pivoting; existing packed terms stay unchanged.

The helper's synthetic article/adjective envelope control retains a noun's exact role while preserving its original guard reason. Additional controls retain PROPN, abstain on unknowns and abstain when only a larger lexical span matches. No per-word repairs or new lexical policy are implemented. The larger pass still requires root review of the final executable driver/protocol before launch.
