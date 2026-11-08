# Korean orthographic reading candidate

This is dormant qualification source. It is not part of the Android application
and does not change the default authored reading path.

`KoreanLetterRules.kt` is generated from the pinned Unicode CLDR
`Latin-ConjoiningJamo.xml` reverse direction. The retained Unicode license applies
to that data and its adaptation. The 67 modern letter mappings and 53 separator
rules encode spelling, including `l`, `g`, `d`, `b` and distinguishing hyphens.
They do not model sound changes or replace original-script speech. The separate
spelling convention is described in [NIKL section 3(8)](https://www.korean.go.kr/front_eng/roman/roman_01.do).

The guard preserves source UTF-16 ranges and every opaque literal. Modern
precomposed Hangul runs are converted independently. Unknown unprotected script,
decomposed/compatibility/archaic jamo and an oversized result withhold the whole
reading while retaining diagnostic pieces. Supporting canonical decomposed
Hangul and chat shorthand remains a separate coverage improvement. URLs and code
can contain original script without falsely being rewritten as language text.

The same 32 frozen cases used by the Apple candidate pass the host JVM guard,
exact-source/literal and warm-output checks. Reading strings match the actual
Mac native candidate in 31 cases. The remaining 16K repeated-syllable control has
three spaces from Core Foundation's four tokenizer ranges; the Kotlin converter
uses one run. These results are not Android execution, fresh conversation
coverage, iOS app integration or acoustic acceptance.

The rule port was compared with system ICU executing the exact pinned rules,
including the complete modern syllable alphabet and a declared adjacent-boundary
matrix. The first run exposed eight start-boundary discrepancies. A generic
non-output boundary marker corrected them; the frozen replay is identical.
This is finite algorithm parity, not hundreds of thousands of language judgments.

Additional 16K controls found recursive Java regex stack exhaustion in a long
identifier. Possessive repetition over disjoint character classes and email
matching anchored at real `@` positions corrected that defect. All six controls
then passed, with all 32 earlier outputs unchanged. The other correction adds
a display boundary after a decomposed Latin name while preserving its exact
characters. Foundation already handled this case; no Swift fix was required.

Measured on host JVM 21 with a 256 MiB heap and one active processor: final
32-case maximum first call was 60.90 ms and warm maximum 24.23 ms. The separate
stress run's maxima were 106.99/27.15 ms. Initial calls include class/JIT work.
These observations are not Android latency or peak memory guarantees.

Reproduction inputs are self-contained except for standard build tools:

1. Run `python3 export_rules.py` and verify the generated hash in the evidence.
2. Compile the three Kotlin files together using Kotlin 2.4.0, JVM target 17,
   the Kotlin standard library and a JDK. Run `co.fallsoft.vipi.ProbeKt` with
   the standard library on its classpath.
3. Compile `upstream_probe.cpp` with a C++17 compiler and the flags returned by
   `pkg-config --cflags --libs icu-i18n`. Supply the XML's CDATA rule body as its
   argument. It executes the upstream reverse rules through ICU independently.
4. `qualify_guard.py` and `qualify_letters.py` accept a build receipt containing
   `java_command`, `upstream_command` and `source_sha256`. Their output paths must
   be new. The guard accepts either the Apple frozen inputs or
   `stress-inputs-r01.json`; neither regenerates expected results from the port.

Before activation, qualify the exact code on an existing Android runtime,
authored-first cache integration, original-script audio/copy, actual chat
interaction and dependency notices. Do not invent readings for unknown names
or call the spelling guide pronunciation-perfect.
