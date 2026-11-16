# All-direction release-floor probe, 2026-11-16

`fixtures.json` freezes 330 new authored messages (three everyday messages per
source language, each evaluated against ten target languages). Concept choice
was informed by the existing vocabulary. These are neither blind held-out data
nor sampled human chats. No pack permissions were generated from these messages.
They measure a finite practical gap, not a conversation-coverage percentage.

Run the **actual bundled default** on both platforms, with source detection and
normal density 0.25; also capture configured-pair direct lookup at density 0.5.
Keep these results separate. Record detection, output/abstention status, exact
source/target spans and readings, output and concept identities, translation and
model-readiness call counts. Zero automatic calls is a required invariant.
A pack loading successfully does not establish useful output for that direction.

The minimum release evidence should include a useful, correctly sensed emitted
single word in every advertised direction under the actual automatic path;
usable Latin readings for emitted non-Latin targets; and actual native speech
synthesis for all eleven target languages. A failed or ambiguous source detector
must remain an explicit abstention. Never force a misidentified source merely to
make the matrix pass. Check protected literals and ambiguous senses separately
when a mapping changes. Three concepts alone do not establish overall quality.

For speech, retain engine, voice, locale, selected emitted text, output duration
and errors. A voice list establishes eligibility; a completed nonempty waveform
establishes synthesis; neither establishes correct pronunciation. Human listening
and native-speaker validation remain separate evidence levels.

`build_fixture.py` reproduces messages and asset SHA-256 bindings without network
access. `audit_assets.py` inventories literal context substrings only. Its 120
rows without a literal context indicate likely catalog gaps, **not** native
failures: it omits raw English→Japanese/Swahili starters, source identification,
token boundaries, density, masks and unchanged-target filtering. All 110 current
packs contain patterns; required Arabic/Chinese/Japanese/Korean pattern readings
contain Latin letters without foreign-script letters. This static property does
not validate the reading's pronunciation.

If these examples inform changes, retain this original capture and label any
rerun as development regression, then assess new authored messages separately.
