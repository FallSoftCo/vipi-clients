# Conversation coverage and expansion

Vipi should make everyday conversation useful for immersion without composing a lesson or requiring a remote language model. Measure what a person actually sees: contextually correct vocabulary with a usable reading, original grammar intact, and sufficient opportunities across ordinary messages. Dictionary size alone cannot establish that.

## Sources in use

| Source | Current use | What it cannot establish |
| --- | --- | --- |
| [NUS SMS](https://github.com/kite1988/nus-sms-corpus), pinned 2015-03-09 release | 87,300 consented English/Chinese SMS messages; informal vocabulary frequencies and reserved native pipeline probes | Modern worldwide demographics, the other eight source languages, or human reference translations |
| [Tatoeba](https://tatoeba.org/en/downloads), pinned 2026-10-24 exports | Ten-language sentences, attributed direct translations, context expansion, component-separated reserved sentences | Representative conversation frequency or uniformly correct translations |
| [Universal Dependencies](https://universaldependencies.org/), pinned 2.18 English EWT and French Rhapsodie training files | Lemmas, inflection, parts of speech and dependency patterns for prioritizing grammar/context coverage | All ten languages or informal chat quality; annotation quality varies |

Tatoeba text retains CC BY 2.0 FR attribution; no audio was downloaded. NUS authors describe their consented release as public domain. Both acquired UD treebanks are CC BY-SA 4.0. Other treebanks are not covered by those licenses. Original archives, exact source revisions, checksums and transformation code remain in research storage. Private user conversations are not collected for this work.

Basis Conversations, Multi3WOZ and Topical-Chat are complementary leads. They are not counted as acquired or qualified. Basis requires separate access/license evaluation; Multi3WOZ covers task-oriented domains rather than all conversation. No external access request or message has been sent.

## Separate measurements

1. **Source recognition:** a source token or phrase exists in a candidate inventory. This is useful for prioritization, not proof of a correct target.
2. **Available immersion:** native processing yields at least one vocabulary replacement. Report both all messages and an independently annotated lexical-opportunity subset, per direction/platform. Short acknowledgements and grammar-only messages remain in the all-message denominator.
3. **Correct displayed vocabulary:** exact intended sense, grammatical scope, readable transliteration where required, and appropriate written form. Wrong provider output is still wrong even when phrase and whole-message models agree.
4. **Grammar/context coverage:** report questions, negation, possession, tense/aspect, number, commands, subordinate clauses, idioms, names, protected literals, spelling variants and multiple sentences separately. Source grammar stays native; these features constrain lexical meaning, not a new mixed-language grammar engine.
5. **User experience:** measure latency, stable layout, continuous alternation, speech and accessibility separately from linguistic counts. Acquisition/fluency requires longitudinal evidence.

Internal release targets are at least 80% of independently identified everyday messages with a lexical opportunity offering useful immersion in **each** launch direction, and at least 99% correct displayed substitutions in that evaluation. Report all-message availability alongside this. Material changes to negation, person, possession or protected text are release failures. These are engineering targets, not achieved results or marketing promises. Do not pool easy English pairs to conceal another pair's failure. Confidence intervals and sampling limits must accompany any population claim; reused directions of one message are not independent samples.

The current 400-message native probe is an initial diagnostic, not enough to certify those targets for all ten languages. Its 200 English and 200 Chinese source messages yield 3,600 directed cases over 18 pairs. Selection is a fixed hash, independent of vocabulary/model results; messages contain 1–280 code points and at least one lexical token. Only 27 of 8,446 reserved messages fail those bounds. It has no invented reference translation. Review must classify actual replacements before accuracy is computed.

## Current measured gap

The full revision-007 dictionary packs use schema 4 and preserve competing source senses without eligible target mappings. Actual replay of the same frozen SMS translations gives these results:

| Measure | Android | Physical iPad |
| --- | ---: | ---: |
| Directed cases | 3,600 | 3,600 |
| Cases with dictionary candidates | 3,209 | 3,243 |
| Cases with selected inline vocabulary | 542 (15.06%) | 597 (16.58%) |
| Selected vocabulary spans | 600 | 664 |
| Cases with research-only relaxed candidates | 2,162 (60.06%) | 2,268 (63.00%) |

These are availability counts, **not correct-substitution rates**. The relaxed policy remains rejected: whole-message translation and lexical agreement can repeat a wrong sense. Ten selected Android failures now have explicit, content-bound diagnostic assessments in `qa/immersion/sms_semantic_findings.json`: informal spelling, incomplete target phrases, contextual senses, compound/name boundaries and source grammar absorbed into a vocabulary span. Their validator confirms the assessed substitutions actually occur in the strict native report. They are selected failures, not an independent random accuracy sample.

The authored path is materially stronger but narrower: 90 signed reviewed-context packs contain 3,567 mappings. Across 3,582 retained authored cases, 3,564 have eligible mappings; 18 quarantined cases are absent. Native lookup/alignment yields immersion in 2,996 Android and 3,250 iPad cases. Those are exact reviewed sentences and finite enumerated variants. Neither these counts nor a growing candidate ledger establishes majority coverage of arbitrary conversations.

Next expansion must improve contextual selection and lexical boundaries on development material, then pass fresh real-message evaluation. Priorities include informal spelling, common inflected forms, names/compounds, phrases containing person or negation, and useful context patterns beyond an exact sentence. These must be measured separately so a new batch of easy nouns cannot conceal unresolved errors. The 400 inspected SMS messages are now diagnostic/regression data, not untouched acceptance material.

## Continuous expansion

The authoring ledger stores immutable revisions, exact spans, sense/usage conditions, readings, source attribution and content-bound assessments. Imports resume transactionally; new revisions invalidate old assessments. Candidate imports, author assessment, quarantine and reviewed exports remain distinct states. Reviewed exports are not automatically release-ready.

Use development-only frequency and grammar audits to select the next concepts/forms. Add attested direct contexts and bounded authored patterns, retaining grammar outside lexical focus. Native matchers accept explicit message-bound source spans and attested target forms; they do not infer arbitrary stems, person or missing readings. Validate new records mechanically, assess their linguistic content, qualify actual Apple/ML Kit output, then evaluate the frozen pipeline on reserved material. Feed aggregate gap categories back to development; do not turn reserved messages into mappings. Once a case informs a fix it is a regression case, and fresh untouched acceptance material is needed.

The source inventory currently includes unreviewed records, so source-recognition reports must say so. The corrected Tatoeba index is revision 002. Its earlier tag-column error and superseded outputs are documented; their immutable receipts remain even after disposable derived databases are retired.

## Reproducible real-message probe

Run substantial processing on OZZZ-OS under `storage-build` with a measured output allowance. Preserve each receipt revision.

```sh
python3 qa/immersion/prepare_sms_probe.py --source vendor-research/conversation/nus-sms-20150309 --output artifacts/sms-probe-NEW --per-language 200 --apple-run-id NNN
python3 qa/immersion/capture_phrase_matrix.py --corpus artifacts/sms-probe-NEW/corpus.json --protocol artifacts/sms-probe-NEW/phrase-protocol.json --capture artifacts/ACTUAL-CAPTURE.json --platform Android --output artifacts/sms-translations-NEW.json
python3 qa/immersion/evaluate_sms_pipeline.py --corpus artifacts/sms-probe-NEW/corpus.json --report artifacts/ACTUAL-NATIVE-ALIGNMENT.json --output artifacts/sms-availability-NEW.json
```

Between these commands, execute the real native `TranslationPhraseDeviceTest`/`TranslationPhraseTests`, then signed-pack `BilingualPipelineDeviceTest`/`BilingualMatrixTests`. Apple uses its own translations; do not label replay of ML Kit captures as Apple translation. Every conversion checks protocol identity, case count, source text, duplicate/missing cases and complete execution. The optional research-candidate export relaxes only the positive-cue requirement and is never the application's display policy. Preserve the strict result alongside it.
