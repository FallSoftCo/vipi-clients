# Whole adjective context experiment — 2026-10-28

The indexed dictionary already supplies many adjective meanings and agreement
forms. This experiment adds context alternatives for actual complete adjective
forms; it generates no translations, spellings, stems, readings or adjective
agreement at runtime.

The filter scans the full pinned en/es candidate dictionaries, independently
of evaluation text. It selects 24,565 English and 28,615 Spanish spellings,
retaining the dictionary release f7093f99b61c1c3c422ede2f10b6930bdeabbedee2f814a0bb624ebc9b89dd24.
The 1,097,728-byte filter SHA is
63f880d055958cafd27d0249acd96afc03a442e4d39870b4a7704a473d02b11c.

Each selected spelling keeps all its existing valid aligned counterparts.
Unknown, different-part-of-speech and competing-meaning observations stay in
the denominator. The compiler accepts only complete mode 1/2 adjective forms
whose explicit dictionary relations intersect. Multiple adjective heads remain
unresolved. A source sentence casts one vote, conflicting translations intersect
rather than multiply its support, and an actual counterpart needs three source
sentences in addition to the 0.98 relation-agreement threshold. This threshold
is not a calibrated accuracy estimate.

The runtime uses the new table only when both actual forms are complete
adjectives and share the qualifying dictionary relation. Existing case,
protected-text, sentence, native window, reading and overflow checks remain.
Noun and verb evidence has separate tables and is not borrowed merely because
a spelling overlaps. All previous witness/alternative tables are preserved.

Fixture 514 combines the 137 previous cases with 40 authored directed adjective
conversations and eight explicit meaning counterexamples. Its SHA is
255a7b387a9b38c1095e63264972a9c9afecbc7273c52c8d3d592f638886668b.
The unchanged data baseline passes on iOS 518. Fixture 513 was retired before
native execution because three initially proposed negatives were unsuitable;
its correction note preserves this authoring error.

The first pipeline launcher referenced a nonexistent renamed filter; its
failure is retained and its waiting child was stopped. Corrected launcher 002
uses the existing generalized filter. The observation pass finishes in 510.45 seconds: 11,106,670 observations
from 2,943,398 retained reference spans, 408,821,760 bytes, SHA
ffffcfd8731a492589bc5fec5b9754802354c9947321cd6524dc1808f7d4714b.
The 107.28-second compiler emits 349,266 adjective alternatives while retaining
2,680,909 unresolved observations as negative evidence. All five prior tables
are checked equal in both directions. Candidate witness 518 is 720,314,368
bytes, SHA c69b82c9d50441e46c6508d44cef6ced006291f78e94635b9a1697edaba5f53b.

Both native baselines 518 agree on 185 cases / 159 spans. Android candidate 519
passes with six additional spans and no losses (159→165). The 40 newly authored
conversation cases gain four adjectives and one previously empty message.
Retained SMS 612 adds free→libre and real→verdadero with no losses:
82→83/200 messages, 112→114 spans. The eight additions have contextual author
assessments in artifacts/adjective-native-review-001; this small gain is not
proportional to the table size. iOS candidate 519/612 adds the identical eight spans with no losses:
86/200 SMS messages and 117 spans. All 185 targeted outputs match exactly.
The three prior iOS-only SMS spans remain; none is a new adjective difference.

The interrupted full-file Mac transfer was replaced with a verified
22,688,904-byte zstd patch against the already verified witness 506. Both base
and patch hashes and the complete reconstructed 720,314,368-byte output hash
are checked before qualification. The superseded partial destination is removed
only after that exact reconstruction. Deltas are QA transport, not a production
language-pack updater. Receipts: adjective-witness-delta-001 and native reports
lexical-coverage-{android,simulator}-518/519/612.json. No data is promoted, no independent precision or 90% coverage is
claimed, and this en/es experiment does not demonstrate all language pairs.

Android universal debug packaging hit the existing 10 GB emulator capacity.
Install receipts 019/020 retain both failures and exact restoration of temporary
QA staging. The existing vipiQaAbi=x86_64 build option is used for the owned
emulator. The x86_64-only APK installs successfully (update 021); source/fixture
qualification then passes. Final app SHA:
8b5b1d40b73747ae3e2803a9cdccbae26573e08f2fb7120b0e8871f52975bd17.
Temporary candidate witness 518 is removed after testing and prior QA witness
506 is hash-restored. Accounts, keys, messages and translation models are preserved.
