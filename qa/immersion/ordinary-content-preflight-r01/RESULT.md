The prospective count completed once over all **7,115 retained annotated EN–ES pairs**. It enumerated **260,900 shared/direct relation rows**, without writing a proof database, annotating, fitting or projecting anything. Existing paired data was selected through the earlier 1,480-head cohort; broadening its focuses preserves that bias.

| Actual source role | Distinct source-focus occurrences | Missing complete supported source form | No complete target POS form in aligned envelope | Any retained shared link | Legacy-clear occurrence |
|---|---:|---:|---:|---:|---:|
| NOUN | 11,790 | 48 | 653 | 10,627 | 1,350 |
| VERB | 7,163 | 2,275 | 5,112 | 5,395 | 0 |
| ADJ | 2,965 | 91 | 519 | 2,338 | 442 |
| ADV | 2,259 | 39 | 730 | 1,413 | 259 |

These are overlapping per-phase sets, **not an exclusive loss funnel**. Shared links can be wrong-POS or incomplete forms; “any link” is not approval. A repeated source focus may have different target witnesses, so missing and available phases can overlap. Legacy-clear applies unchanged helper reasons plus exact-role, single-target-token and alignment/mask checks; it remains unapproved for display and is not new message coverage. There are only two noun and one adverb *individual source occurrences* with multiple legacy-clear target faces; that is not a count of source vocabulary keys having alternatives across different occurrences.

The paired-occurrence counts are 11,969 noun, 7,302 verb, 3,006 adjective and 2,290 adverb. They exceed distinct source focuses because one source can have several parallel pairs. Candidate form/term rows further multiply alternatives; none of these counts represents independent corpus sentences or original-message coverage gains.

| Source occurrence role (not necessarily candidate dictionary POS) | Explicit shared rows | Nonexplicit shared rows | Existing direct candidate rows |
|---|---:|---:|---:|
| NOUN | 52,365 | 4,872 | 487 |
| VERB | 179,301 | 6,709 | 3 |
| ADJ | 13,049 | 855 | 10 |
| ADV | 2,559 | 687 | 3 |

Direct candidates remain the original 17 published noun relations with unresolved source-entry/sense identity. Their presence at an actual adjective/adverb/verb occurrence is contrary role evidence, not a new direct POS relation. No source-name override was applied; name-only guard flags survive separately.

The verb restriction is not merely `unsupported_pos`. Of shared rows at VERB occurrences, 185,017 have that historical reason, 172,656 have unsupported form mode, 172,494 incomplete form, 172,683 dictionary/actual-role mismatch and 96,541 crossing union edges; reasons overlap. All remain immutable. Most apparent relations are not valid complete verb candidates, and noun-number equality cannot rescue them. The feature census retains present/infinitive/person alternatives, past/participle forms and explicit attested-past carrier features requiring a finite clause. It provides concrete evidence for the additive proposed form/context contract, not permission to relax the old guard globally.

Adjective/adverb results likewise do not imply output acceptance. The source-role inventory is corpus-token geometry, not a new native-device qualification. Full degree, source grammatical function and target agreement still need the declared policies. Target gender agreement differences must be separated from semantic changes such as polarity, number, tense/person and degree.

### Exact prospective size

The count hashes the exact proposed compact serialized objects, deduplicating forms/units and comparing object IDs against the retained parent database. It writes only metadata.

| Prospective retained material | Rows | Logical bytes including object ID/kind |
|---|---:|---:|
| Dictionary forms with all terms | 35,941 | 98,769,912 |
| Occurrence-specific dictionary units/form references | 53,986 | 39,688,350 |
| Prospective relations with raw form/role evidence | 260,900 | 697,068,316 |
| Total objects | 350,827 | 835,526,578 |
| Already reusable parent objects | 20,523 | 20,889,039 |
| New objects | 330,304 | 814,637,539 |
| Additional relation index identifier payload | — | 39,703,714 |

New logical object+index payload is **854,341,253 bytes**. Relation JSON UTF8 size: minimum 1,850 B, median 2,622 B, p90 2,717 B, p99 2,807 B, maximum 3,292 B. This is measured logical payload, not a physical SQLite estimate pretending to be exact. Parent evidence remains referenced, not copied.

The earlier complete join used 313,032,704 physical bytes for 200,459,849 logical bytes (about 1.56×). Applying that observed ratio gives approximately **1.33 GB physical** for this proposed representation, before any contract-driven schema additions. The previous tentative 1 GiB physical ceiling is therefore too tight. Proposed, **not executed**: up to 1.5 GiB database, 1.75 GiB aggregate output and 2 GiB reservation, unchanged 8 GiB free floor. Recheck the finalized schema's prospective bytes and include journal/metadata overhead before materialization; distribution/schema uncertainty remains. No alternative may be dropped to meet a cap. Root must review the contract and bound before any proof database is created.

### Interpretation, guard gap and next decision

The count confirms available data beyond the special noun cohort, but the legacy-clear yield is far smaller than raw relation count. It does not yet establish a useful-coverage gain on the original 9,535 messages. The next experiment must broaden ordinary source focuses rather than permanently selecting only source-name exceptions, while retaining distinct semantic-feature and mixed-grammar form checks.

[PROPOSED_CONTRACT_R02.md](PROPOSED_CONTRACT_R02.md) is an additive **post-count proposal**, not an overwritten predeclared policy. It specifies ordinary noun controls, form-neutral lexical content, and context-bound inflected forms; finite forms whose person/tense is source-unresolved cannot fall back as unrestricted unigrams. Head-dependent adjective forms need scoped evidence. It preserves contrary readings without an all-senses-agree gate, and introduces no grammar transfer or per-word target repair. A candidate remains unavailable when the required context/feature evidence is absent; the eventual actual comparison policy must be separately frozen before predictions.

Shared rows compute mutual-anchor and union-crossing reasons. The current direct-candidate serialization retains exact alignment references and source/target masks **but does not compute those two direct rejection flags**; no direct row is display-approved. Full direct alignment checking is required at materialization, and direct raw counts cannot be represented as guard-equivalent to shared rows.

Execution was **80.639 seconds / 330,571,776 B VmHWM**, within one CPU / 1 GiB address space / 120 seconds. Result JSON is **56,832 B**, SHA `da6bfde1b8c591670023a934e17dc02650c4577a036a77539bda99cfd542dc3f`. All selected pairs completed, all input hashes passed, and every candidate relation identity contributes to the final sorted-ID hash. No alternatives were sampled or truncated. Launch checked code/protocol/contract SHAs; count.py itself verifies code and input hashes but not the contract file. Closure separately verifies the original contract SHA `fac577684ab7ec09871fcda9bcffa2ada9938478ef83d49766169f215ae0edf3`. No count replay, broad proof materialization, new annotation, fitting, projection, native app change or activation occurred.

Private evidence: `/home/ai/Development/investigations/vipi-ordinary-content-preflight-20261109-r01`. Production metadata and immutable input references: `/srv/fallsoft/staging/vipi-ordinary-content-preflight-20261109-r01`. The full prior proof database and helper snapshots remain unchanged.

### Baseline overlap and smaller alternative

The 1,350/442/259 legacy-clear focuses are **not known new coverage**; many may already occur in the broad baseline. The genuinely new data path is occurrence-qualified complete-form evidence across all content focuses, rather than restriction to newly admitted name-only nouns. Before building its full evidence store, measure exact baseline overlap by source context/focus, target face/form/reading and current message position. Separate extra evidence for an old candidate from new alternatives, new eligible focuses, selection changes and newly useful complete outputs on all 9,535 messages. The current count cannot answer that overlap question.

Full raw rejected-relation materialization is optional. The measured 1.5 GiB proposal describes one complete physical representation, not necessary progress toward coverage. Existing immutable inputs plus count/identity hashes preserve reconstruction; a bounded compact accepted/competing-candidate comparison can be more useful.

The additive contract therefore prioritizes a smaller context-scoped noun branch: ordinary baseline versus the existing narrow source-name-only exception **only with independently supported covering multiword source context**, live lowercase NOUN/content evidence, unchanged target/form/number/alignment/masks and no exception unigram fallback. The earlier source-name experiment demonstrated original-message reach and reviewed useful additions, so this branch has a more direct coverage rationale than raw all-POS row growth. However, 8,331 name-guard noun counts are paired focuses, not new messages; the previous season error already had multiword context, and names can span multiple words. This proposal neither proves a fix nor silently approves the exception. Separately represented direct-English candidate evidence may address missing targets, while retaining unresolved identities and its diagnostic scope. Details and required baseline-overlap/whole-message validation are in the additive contract. Root review is required before either proposed comparison or materialization.
