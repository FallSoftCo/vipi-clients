# Deterministic ordinary-pinyin candidate

This is research data and a native implementation handoff, **not an enabled
application dependency or a production accuracy claim**. No network model,
JavaScript runtime or shared application engine is selected by this experiment.
Swift and Kotlin can consume the same versioned language data independently.

The unmodified upstream `pinyin-pro` 3.29.5 package was fetched from its official
npm registry distribution, checked against the registry's SHA-512 integrity and
pinned by SHA-256. The retained archive includes its MIT license and readable
ES modules. Preserve that notice when reusing the implementation or data.

`ordinary-data.json` contains 21,132 character entries and 4,185 phrase patterns
from that exact package. The maximum phrase length is five Unicode scalars.
Tone marks are removed only from reading values through the upstream conversion
function; `ü` and `ê` remain distinct. Protected original names, identifiers,
URLs and source text must never undergo accent stripping. All alternative
character readings remain in the artifact. Choosing the first alternative is
the upstream default, **not proof that a character is unambiguous in context**.

## Native contract to qualify

- Preserve exact original UTF-16 ranges while matching Unicode scalars. Treat
  opaque identifiers as complete protected ranges; do not match inside them.
- Use the pinned upstream phrase probabilities and selection semantics, with
  surname mode off. Preserve deterministic tie handling. Neither a longest
  prefix implementation nor independent character conversion is automatically
  equivalent to the upstream phrase selector.
- Unmatched characters use the first dictionary reading and the two documented
  general rules for `了` and `々`. These are inherited upstream rules with
  limitations, not grammar inference supplied by Vipi. Tone sandhi has no effect
  on the ordinary tone-free sequence.
- Return scalar-aligned reading pieces. The library's default string output
  inserts spaces inside Latin names and links and is unsuitable for the app.
  Preserve original literals and punctuation, adding display separators only
  outside protected ranges. A known phrase can group its own syllables.
- Unknown unprotected Han or other unresolved script must stay explicit;
  Latin-only completion and dictionary membership do not certify meaning.
  Keep reviewed authored-reference precedence and source-script audio.
- Compute once per completed translation off rendering work, retain immutable
  results, and reject stale conversation/language generations. Do not run the
  reader on each flip or SwiftUI/Compose recomposition.

Parity against this frozen upstream is an implementation check, not semantic
acceptance. The first diagnostic reused 104 authored Chinese references,
32 retained NUS messages and four seen structural controls. Raw marked output,
tone errors, unknown characters and source ambiguity are retained privately.
Ordinary pinyin and acoustic pronunciation are evaluated separately; audio
remains the pronunciation authority. Independent review and native execution
remain required before any application integration.

## Reproduction

After checking the archive hash in `provenance.json`, extract the retained
archive to an owned disk-backed directory. It contains a top-level `package/`.
No dependency installation or package scripts are required:

```sh
node export-data.mjs /absolute/path/package /absolute/path/new-ordinary-data.json
```

The generator refuses an existing output. Compare the resulting bytes with the
hash in `provenance.json`. Native build and resource-admission rules still apply.

Primary source: [pinyin-pro](https://github.com/zh-lx/pinyin-pro),
[versioned package metadata](https://registry.npmjs.org/pinyin-pro/3.29.5).
