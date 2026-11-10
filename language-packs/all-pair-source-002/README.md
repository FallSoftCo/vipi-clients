# Finite all-pair source frames, revision 002

This portable package regenerates 108 additional directed source-frame packs and
their hash-pinned index. It excludes `en-ja` and `en-sw`: their shipped starter
and source-frame assets and provider priority remain unchanged. Asset presence
does not activate native providers; native promotion is a separate decision.

The reviewed content consists of the retained finite contextual/formula grid
and eight exact standalone compound groups. Japanese bare `駅` is omitted from
standalone source lookup; its contextual railway entry is narrowed to `電車の駅`.
Whole-sentence formulas and selected Chinese clause-final guards require the
qualified native variant contract. Token boundaries, density budgets, protected
literals and language-direction checks remain unchanged.

Generate into a new, disk-backed staging directory:

```sh
python3 language-packs/all-pair-source-002/build.py --output ./source-frame-staging-002
```

Verify canonical bytes without writing:

```sh
python3 language-packs/all-pair-source-002/build.py --verify data/immersion
```

The compiler uses only the checked-in files beside it. It does not read private
investigation directories, decompress dictionaries, invoke a translation model,
or access the network. It refuses to overwrite an existing output directory.
All 216 generated pack/manifest files reproduce the frozen reviewed r02 bytes.
The additional index is `all-pair-source-catalog-001.json`, schema
`vipi-bundled-source-frame-index-1`, with exactly 108 unique entries.

Inputs retain the shared concept IDs, exact contexts, target faces, Latin-letter
readings, original authored record IDs and record/evidence hashes.
`authored-overrides-r01.json` records deliberate source-context changes and
withheld concepts; `review-manifest.json` records the subsequent sentence/Chinese
boundary contract and Japanese railway correction. `standalone-examples.json`
preserves the ordinary source-language examples and scope decisions.

These are agent-authored and agent-reviewed finite records, with independent
review of native outputs; they are not native-human gold or a population
accuracy estimate. The output reviewer also participated in data authorship,
so the review is independent of platform implementation, not blind linguistic
review. Existing dictionary row counts and bidirectional evidence do not grant
blanket source-only permission. No 90% or conversation-wide coverage is claimed.

The historical review manifest remains hash-identical to the frozen candidate
and retains its pending-root-acceptance status. Later integration/review receipts
record subsequent decisions without rewriting that evidence. This package is
not a public-source release or a customer/store readiness declaration.
