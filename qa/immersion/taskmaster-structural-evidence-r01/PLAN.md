# Proposed Taskmaster source-structure comparison — not executed

Use the already retained EN→ES Apertium pipeline as an **offline evidence comparison**, stopping before surface generation. Compare its bilingual default, contextual lexical selection and source-pattern transfer traces on all frozen Taskmaster200 messages. This can distinguish a different dictionary default from actual contextual disambiguation, and test whether a complete source construction supplies useful phrase-lookup evidence. It cannot assume that either the pipeline or cached MT is correct.

## What exists and what was already tested

- Production root `/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01/root`: all184 retained files freshly rehashed against the prior protocol;13,260,471 logical bytes including symlink targets counted as files. Apertium3.9.4, lttoolbox3.7.6, lex-tools0.4.2, eng-spa0.8.1. No executable was launched during this inspection.
- The original20-case full transfer probe already captured every stage:8.52s,38.6MB maximum child RSS. It showed useful noun/verb and construction handling, but also Please→Complacer, country-music→país and on-my-way→en-mi-manera failures. Do not repeat that probe or portray transfer as new/qualified meaning authority.
- The32-pair occurrence-role comparison mapped74/80 focus tokens and agreed with frozen agent roles on those74, including Spanish verbal pediste/llamas. The later14,004-endpoint batch and corpus join are complete. These are not Taskmaster contextual-sense results.
- The781-record newly-common-noun lexical-selection comparison already ran biltrans and LRX: six alternative-list reductions, **zero first-choice changes**. Its matching631-rule LRX source is retained; the binary is141,085B. That narrow negative does not establish no effect for Taskmaster's full range of roles.
- HFST3.16.0/lexd1.3.1 closure remains locally retained,27,812,077B in its recorded tool receipt. Its Swahili morphology probe compiled a1,276,945B analyzer and933,641B generator, but had missing/common-form and person/negation errors. It is neither EN→ES contextual grammar nor bilingual lexical selection. No HFST executable is on production PATH and none is needed here.
- VISL CG-3 is a distinct constraint-grammar engine, **not** the retained LRX module. No CG stage occurs in this pinned EN→ES mode; no CG executable is on production PATH and no qualified English grammar closure was found in these retained experiment paths. Installing a generic engine would not supply an English grammar. No CG/HFST acquisition is proposed.

The actual pair mode and upstream [versioned modes](https://raw.githubusercontent.com/apertium/apertium-eng-spa/v0.8.1/modes.xml) use an HMM tagger, pretransfer, genitive rewrite, bidix, LRX and three transfer stages. [LRX documentation](https://wiki.apertium.org/wiki/Constraint-based_lexical_selection_module) places contextual target-choice rules after bidix. [Chunking documentation](https://wiki.apertium.org/wiki/Chunking) describes source-pattern-driven shallow chunks, not a complete dependency parse. [HFST](https://hfst.github.io/) supplies morphology machinery; [CG-3 documentation](https://edu.visl.dk/cg3/single/) supplies contextual reading-selection operations but requires a language grammar.

## Exact proposed command contract

Set `R` to the existing root above, `B=$R/usr/bin`, `D=$R/usr/share/apertium/apertium-eng-spa`, `LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu`, UTF-8 locale. Execute argv arrays, one input message per process/stage, retaining each stdout/stderr/exit/hash; no shell interpolation of text. Each downstream stage reads the preceding retained bytes:

1. `$B/apertium-destxt` with exact UTF-8 source on stdin.
2. `$B/lt-proc $D/eng-spa.automorf.bin` (all morphological analyses).
3. `$B/apertium-tagger -g -p $D/eng-spa.prob` (selected analysis plus surface). Derive normal stream by removing only the surface field; on the first16 hash-selected IDs independently run normal `-g` against the SAME morphology bytes and require exact equality before proceeding. No model refit.
4. `$B/apertium-pretransfer`.
5. `$B/apertium-transfer -n -T $D/apertium-eng-spa.eng-spa.genitive.t1x $D/eng-spa.genitive.bin`.
6. `$B/lt-proc -b $D/eng-spa.autobil.bin` — **dictionary-default control**, all alternatives retained.
7. `$B/lrx-proc -m -t $D/eng-spa.autolex.bin` — contextual alternative list and first-choice comparison. Pinned `-m` is a deprecated no-op, not an ME classifier.
8. `$B/apertium-transfer -b -T $D/apertium-eng-spa.eng-spa.t1x $D/eng-spa.t1x.bin` — first chunks and actual trace.
9. `$B/apertium-interchunk -t $D/apertium-eng-spa.eng-spa.t2x $D/eng-spa.t2x.bin`.
10. `$B/apertium-postchunk -t $D/apertium-eng-spa.eng-spa.t3x $D/eng-spa.t3x.bin` — lexical output only; **no generation/reformatter or full translated sentence**.

`-T` is the pinned transfer-tools trace (also enables `-t`), documented in [3.9.4 source](https://raw.githubusercontent.com/apertium/apertium/v3.9.4/apertium/apertium_transfer.cc). The [implementation](https://raw.githubusercontent.com/apertium/apertium/v3.9.4/apertium/transfer.cc) traces temporary words, buffer positions, matched rules and consumption/rejection. A plain Rule trace is a match attempt, not proof that a rule committed. Retain raw traces; only label accepted consumption when the trace supports it. No custom grammar or engine patch.

## Mapping and comparison frozen before execution

Retain all200 IDs,185 unique texts and14 null cached-target rows. Process each row independently; no target/provider call. Bind the exact original input SHA `8ced39c191466dcd6a4f86a3dd738444c8e8d58609f1dbd1d06e46b001c5dc6d`, prior output, frozen agent labels, latest native-role observations and source dictionary identities.

Map morphological surfaces left-to-right to exact original UTF16 spans, preserving escapes, punctuation and complete multiword units. Require exact full lexical-unit sequence/source-header parity through pretransfer/genitive/bidix/LRX for focus correspondence, as previously qualified. If rewritten, retain stage evidence but mark mapping unavailable; never first-lemma match a repeated word. Trace-based chunk attribution requires an unambiguous ordered consumed source interval and complete original units. No fabricated transfer-output alignment; ambiguous/rejected trace paths remain unassessable. Postchunk output is retained structural evidence, not token-aligned display permission.

Primary denominators: all200 messages,1,587 native words, all172 existing scope edges (193 lexeme records), all A129/B199 selected spans. For each exact-mapped focus retain morphological alternatives, HMM source reading, bidix defaults/all alternatives, LRX first/all alternatives and actual rule traces. Compare dictionary source POS to Apertium versus frozen Apple tags. Compare selected target lemma to the exact existing candidate target lexeme/headword and full form tags where supported; retain unknown, multiword, inflected/underspecified and incompatible forms separately. Mere lemma coincidence is not a qualified surface replacement. No new target faces are emitted.

Report default versus LRX changes independently from source-role disagreements and multiword structural matches. Classify evidence as unchanged support, conflicting role/target choice, absent candidate, unknown mapping, or potential source-construction support. Reuse frozen agent labels only to describe the original selected spans' tradeoffs, including all11 flagged cases; do not tune to them or invent labels for unreviewed alternatives. Any meaningful new alternative would need a separate anonymous source/options packet without parallel references before semantic approval.

## Runtime, bytes and dependencies

No new engine/model/data bytes or installation. Exact existing EN→ES assets include morphology397,185B, HMM47,346B, bidix632,815B, LRX141,085B, genitive XML/bin5,183/818B, first transfer XML/bin650,963/34,828B, interchunk173,009/17,969B and postchunk85,346/3,897B. Full manifests are private, hash-bound to the retained closure.

Reuse private libapertium, liblttoolbox, libapertium-lex-tools and libirstlm plus the already-qualified system loader/libc/libstdc++/libgcc/ICU74/libxml2/z/lzma libraries. Prior runtime-preflight records exact resolution; this metadata inspection did not run `ldd` or binaries. `readelf` was absent, so the failed metadata attempt is retained and the completed inventory explicitly uses prior dependency evidence. No dependency install is justified.

Proposed one CPU/nice10,1GiB AS,300s engine stage and120s parse/comparison,64MiB aggregate output,128MiB additional disk plus8GiB floor. Per-message execution is deliberately simple: prior20 full pipelines took8.52s; linear200 estimate≈85s, not a guaranteed deadline. Prior734-endpoint lexical capture179.7s included Python dataset work; these measurements support the ceiling.64MiB is a prospective cap, not a claimed measured output: it covers200 raw stages/traces and compact comparisons, with per-write accounting/retained failure and no silent truncation. Record actual child/parent memory and timings. Fresh capacity and hash/dependency checks precede launch, which is **not authorized by this preparation document**.

## Local phrase lookup boundary and licenses

If existing rules show useful contextual distinctions, retain an offline evidence record keyed by the exact source construction, focus interval, rule/data identity and target lexical alternatives. Such records could inform a separately reviewed local phrase pack. They do not approve a noun/name automatically, override source masks, change caller-known state, replace the current source-first path or install this engine in clients. Recognition can protect a complete unit without emitting a target. An absent or wrong rule remains a measured limitation, not a reason to hand-write exceptions for these messages.

Retained package copyright files identify Apertium mainly GPL-2+ with LGPL components; lttoolbox GPL-2+ with component exceptions; pair data GPL-2/GPL-2+ by file; lex-tools GPL-3/GPL-3+ with GPL-2+ components. [Pair COPYING](https://raw.githubusercontent.com/apertium/apertium-eng-spa/v0.8.1/COPYING) and [lttoolbox COPYING](https://raw.githubusercontent.com/apertium/lttoolbox/v3.7.6/COPYING) are retained-source references, not blanket relicensing. HFST executable receipt reports GPLv3; CG-3 documents GPLv3+ and separate proprietary licensing. Language dictionaries/grammars have their own licenses; engine licensing does not cover an unacquired grammar. Offline research readiness is not native redistribution clearance. No new architecture commitment is made.
