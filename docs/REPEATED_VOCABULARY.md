# Repeated identical vocabulary — 2026-10-28

The native frame matcher can align repeated identical assessed whole units
when source and target occurrence counts match exactly. Each occurrence
displays the same written target and reading; ordering those equivalent
occurrences does not claim general sentence or phrase alignment.

Only records whose source and target are both explicitly marked whole lexical
units can use this path. Existing exact text, native word boundaries, protected
text, case, meaning, reading and overflow checks remain. Attached carriers and
larger phrase frames keep their previous unique-occurrence requirement.
Different counts or a present alternative with an inconsistent count abstain.

An absent target alias still contributes its source meaning. A different
meaning vetoes all claims for that source focus; an absent spelling of the same
meaning does not manufacture an occurrence-count conflict. The first native
attempt retained that false veto and failed the repeated-week positives.
Android/iOS 516 preserve the failure. No failed run is accepted as qualification.

The authoring probes add “next week, this week” and “próxima semana, esta semana”
in both directions, plus missing/extra targets, number disagreement and a
name-like capitalized Week. Core checks also retain a contrary source meaning
whose translation is absent, and an absent same-meaning alias. Fixture 512
contains 137 cases, SHA eb85a6b9d1f93c211fb8adbfa4727ff645d43a9a7c360ebcbd0459e4cfe61f49.

Final Android/iOS 517 both pass the 137-case fixture with identical 120
selected spans. Retained SMS 611 gains the same previously empty message and
two week→semana flips: Android 81→82/200 messages, 110→112 spans; iOS 84→85/200,
113→115 spans. Three older platform differences remain. No prior span is lost.

Broad 602-case replay gains 47 spans in 16 directed cases, with zero losses
on each platform. Android 017→018 changes 256→264 messages and 364→411 spans;
iOS 018→019 changes 257→265 messages and 364→411 spans. The exact additions
match across platforms. These cases repeat a few source texts across language
directions; they are not 16 independently sampled conversational topics.
Added target-language spans include Swahili siku/kitabu, Chinese 月 (yuè) and
天 (tiān), and Japanese 本 (hon).

artifacts/repeated-unit-review-001/assessment.json retains the source,
translation, geometry and author assessment of all 49 additions across 17
directed messages (broad + SMS). The added vocabulary matches the intended
meaning in those contexts. Several surrounding full translations remain poor;
this review neither certifies those translations nor estimates independent
semantic precision.

Final source hashes are in repeated-unit-source-003/receipt.json. Native
reports are lexical-coverage-{android,simulator}-517/611.json and
bundled-conversations-android-018.json / simulator-019.json. Corresponding
repeated-unit comparison/parity directories retain full inputs and changes.
The final Android app SHA is
775a3e2712ec72cea106cfd72f81223a2e7921f932f8f836c4bcb7295d02efd8.
Android core/build checks and Swift core checks pass; replay uses retained
translations, not fresh translation-model evaluation. Exact QA witness
restoration is recorded by the Android workflow.

This code has not changed accepted lexical 009 or phrase 022 data, published a
language pack, or established majority/90% conversation coverage. No new
physical iPad, screen-reader or acoustic acceptance is claimed.
