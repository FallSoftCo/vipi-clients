# Native Japanese token geometry

This diagnostic CLI supplies unchanged Japanese word, punctuation, symbol and protected-literal spans for a separately frozen corpus experiment. It does not translate, stem, infer senses, request models or alter the app. It is not the English–Swahili/Spanish corpus run.

`contract.json`, `inputs.json` and `TokenizeJapanese.swift` were frozen before native execution. The unchanged 37 inputs comprise retained authored/structural diagnostics and two retained actual Japanese provider outputs. Every row carries source provenance. Qualification on macOS 26.6.2 reconstructed all 36 accepted originals exactly; the 16,385 UTF-16-unit control was explicitly rejected. All 37 first/warm results matched. The independent Python audit verifies original UTF-8, scalar and UTF-16 ranges, partitions, literal isolation and surface kinds.

The first implementation is retained in `../apple-japanese-tokenization-r01`. NLTokenizer can return emoji and currency through its word callback, and split a decomposed Latin name inside a grapheme. R02 classifies the exact surface and coalesces only adjacent native ranges whose shared boundary cuts one original grapheme. Raw whole-text native ranges remain untouched. There are no sentence-specific rules.

## Building and running

Use an authorized macOS development environment and its existing SDK/module cache. The measured run used Swift language mode 6, `-O`, macOS 26.5 SDK and deployment target `arm64-apple-macosx26.4`. No package dependency is required.

```sh
xcrun swiftc -parse-as-library -swift-version 6 -O \
  -sdk "$(xcrun --sdk macosx --show-sdk-path)" \
  -target arm64-apple-macosx26.4 \
  -module-cache-path "$EXISTING_MODULE_CACHE" \
  TokenizeJapanese.swift -o tokenize-japanese
./tokenize-japanese inputs.json NEW_OUTPUT_DIRECTORY EXPECTED_INPUT_SHA256
```

The output directory must not exist. Input schema is `vipi.japanese-tokenization-inputs.1` with `cases:[{id,text,original_sha256}]`; additional provenance fields are retained by the input protocol but ignored by the native decoder. Limits are 512 rows, 16,384 UTF-16 units per input and 8 MiB serialized output. Freeze the next corpus input and its hash separately. A limit failure is an incomplete run, even if some rows were already written.

Each JSONL row contains `first.raw_native_words`, projected `first.tokens`, explicit `first.separators`, `first.protected_ranges`, diagnostics and timing. Offsets are half-open in original Unicode scalars (`codepoints`) and UTF-16 units (`utf16`). Sort projected tokens plus separators by start to reconstruct the original exactly. `kind=other` does not imply a linguistic word. Preserve raw native and projected geometry separately. The warm result is compared in memory and retained by hash/equality; it is not duplicated in the output.

Non-ASCII URI bodies and undelimited Japanese suffixes remain conservatively opaque with `uri_non_ascii_boundary_ambiguous`; consumers must retain that limitation rather than infer a correct URI endpoint. Identifiers are never split partly into learnable tokens. No normalization or reading conversion is performed.

`audit_capture.py INPUTS CAPTURE BASELINE_CAPTURE NEW_AUDIT` independently checks the bounded r02 capture against retained r01 geometry. `independent-audit.json` and `qualification.json` bind complete native results, source/executable hashes, resource admission and initial failures. The capture is diagnostic geometry, not semantic alignment or population coverage.
