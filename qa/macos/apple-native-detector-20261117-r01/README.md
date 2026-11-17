# Apple local detector candidate

This is a bounded macOS 26.6 native feasibility check, not an iOS or general
language-accuracy claim. Protected literals and existing length/letter bounds
are unchanged. Automatic requests require two letter-bearing NLTokenizer word
segments; reliable supported CLD2 wins, and only a CLD2 abstention may use the
unrestricted NLLanguageRecognizer top result at confidence 0.70 or greater.
Unsupported top languages abstain. Full-translation requests retain the prior
CLD2-only path and do not acquire the new two-word gate. Exact references and
explicit language selections bypass automatic identification as before.

`result-r04.json` records 32 native wrapper cases and cancellation, using the
actual MessageLanguage, literal-mask source, C++ adapter, retained CLD2 object
closure and installed macOS NaturalLanguage framework. This includes 11
representative languages, three short English inputs, CJK tokenization,
Swahili, one-word ambiguous inputs, protected literals, Polish, mixed script,
size and threshold boundaries. NL classified the Swahili sample as Polish;
reliable CLD2 correctly took precedence. The two synthetic mixed-language
conflicts in `mixed-supported-conflicts.jsonl` demonstrate that legacy CLD2
precedence can preserve an imperfect answer and does not prove accuracy.
System model version/hash is not exposed by this probe.

`result-r02.json` records eight actual macOS LookupFirst + bundled production
starter/frame provider routes, using the candidate wrapper and retained r14
resources. “I love music.” and “I heard music.” produced 音楽 / ongaku and
muziki with zero readiness, translation or alignment callbacks. Exact “I like
music.” bypassed classification; explicit one-word `music` with an English
override also bypassed classification. The route harness invokes the same
intent-specific detector closure as ConversationImmersion but is not an app
or Simulator run. `core-source-comparison.json` verifies 19 VipiCore source
files against the retained production snapshot; 15 bundled-provider files
were also hash-compared. The focused XCTest source was typechecked natively;
it was not run in an iOS test host. The separate Simulator run, if completed,
must be reported independently.
