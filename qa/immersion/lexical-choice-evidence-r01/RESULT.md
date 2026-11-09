The existing corpus contains a limited lexical-choice pool, but it is not yet trustworthy training supervision. Missing direct source relations and unverified occurrence roles both matter. The next decisive work is to trace relation provenance, then qualify bilingual occurrence roles; fitting a selector now would learn some dictionary-induced mistakes.

R02 completed in 10.28s with 114,847,744 bytes VmHWM. Its census is byte-identical to the retained r01 census. Full audit evidence is 3,768,233 bytes; census 3,094,072; name inventory 13,960. All outputs and receipts were verified locally. The failed r01 evidence remains intact; no fitting, ranking, projection, activation or cleanup occurred.

| Census over the frozen 1,480 heads | Heads |
|---|---:|
| Any supported alternative under diagnostic rules | 1,480 |
| Multiple target lexemes | 191 |
| Multiple emitted spellings | 102 |
| Multiple casefolded emitted forms | 91 |
| Only capitalization distinguishes emitted spellings | 11 |
| Multiple lexemes but one casefolded emitted form | 102 |
| At least two casefolded forms, each with two components | 43 |

The last count is a conservative lower bound based on each retained identity's component count, without summing overlapping form identities. The two distinct counts of 102 do not represent the same set. Multiple lexemes can emit one valid spelling; synonyms can offer several valid spellings. Neither is automatically an error to disambiguate. The earlier 697 keys with multiple whole-phrase targets greatly overstate the noun-choice pool.

All 29 added review emissions are individually interpreted in [result.json](result.json), including every admitted target identity, independent source/pair/component count and diagnostic rejection overlap. The audit retains 761 occurrence records from 641 full parallel pairs and 624 distinct source endpoints, with 285 deduplicated dictionary form records and 124 supported link records. Source-window features count a repeated English endpoint once per target identity even when several Spanish translations exist. These records are inspectable evidence, not 761 independently certified translations.

Three findings determine the next step:

- **Relation completeness:** the failing `the fall` lookup has only caída witnesses. Raw unigram `fall` variants also include otoño twice, but the supported noun census for both keys admits only caída. Detailed complete English noun forms link decline, gravity and loss of status, or have no linked terms; they do not expose an autumn link. This establishes a gap in this qualifying relation path, not absence of autumn from the corpus or a gold label for each raw pair.
- **Actual occurrence roles:** `order→pedido` includes the source verb in “I did not order this” and target participle in “No he pedido esto,” yet passes the dictionary noun-pair evidence test. Dictionary POS is not occurrence POS. Other alternatives, such as esposo/marido and lugares/sitios, are often ordinary synonyms; their frequencies alone do not identify correctness.
- **Name spans:** the failed title has 18 native windows covering its full span, zero retained covering source contexts, no spanning source mask and no protected range. Generic ball alternatives (pelota/bola/balón) and a single generic dragon witness do not preserve the title. Lexical selection and source-span protection are separate problems.

The ±2-token source features do not encode an entire sentence or prior conversation. In the season error, winter is outside that feature window. Full parallel witnesses remain retained for later feature choices; this pass neither computes a full-context classifier nor claims local features suffice.

The smallest decisive follow-on is one frozen provenance-and-role qualification, without a new selector:

1. First trace raw/native gloss provenance through the existing builder into packed linked terms for the same source inventory, preserving all 29 audit controls. Separate existing explicit pivot links, eligible direct-English nonexplicit relations, absent relations and ambiguous source-entry matches. The earlier [source-completeness audit](../native-source-annotations-r01/conditional-agreement-result.md) established that `explicit=0` can represent valid direct-English evidence. [build_native_gloss_links.py](../../../language-packs/build_native_gloss_links.py) also requires a unique English entry and one qualifying gloss leaf; multiple same-POS entries may prevent a link from being built at all. Trace the actual autumn records and exact rejection reason before concluding that merely dropping `explicit=true` repairs it. No fabricated unique source-sense identity or blanket flag relaxation.
2. Then compare dictionary-only support against actual full-sentence source **and target** occurrence roles over the same broad paired inventory. Keep the supplied corpus token boundaries and independently qualify that tagging regime. The official [OpenNLP model inventory](https://opennlp.apache.org/models.html) lists English UD-EWT and Spanish UD-GSD POS models with hashes/signatures; the Spanish model is a research lead, not downloaded, qualified or run here. A source-only role check would miss target-participle contamination. Preserve all failures and unknown roles instead of converting tag scores into semantic truth.

If those prerequisites leave a meaningful choice pool, the scalable representation is ambiguous direct source spelling/POS→target native lexeme/form evidence, alongside explicit pivot evidence, without forcing a unique fine-grained source sense. A later offline Apertium-style weighted context-rule comparison can choose among retained target forms, with default-frequency control and component-separated evaluation. Apertium's task is target choice, not necessarily fine-grained sense choice; its parallel-corpus rule workflow and compiled lexical selector are relevant mechanisms, not proof that this data is ready. See [lexical selection](https://wiki.apertium.org/wiki/Lexical_selection), [parallel-corpus learning](https://wiki.apertium.org/wiki/Learning_rules_from_parallel_and_non-parallel_corpora), and [constraint-based selector](https://wiki.apertium.org/wiki/Constraint-based_lexical_selection_module). No fit, model download/run, per-word patch or all-senses-agree gate is authorized by this result.

[completion-receipt.json](completion-receipt.json) binds exact outputs and the local summary. The full private evidence is under `/home/ai/Development/investigations/vipi-lexical-choice-evidence-20261109-r01/occurrences-r02/`.
