# Signed installer fixtures

These small public synthetic fixtures are consumed only by native tests. They are
not production language packs or production signing keys. The existing generator
sources and exact output hashes are recorded in `signed-pack-fixtures-provenance.json`.

Regenerate into a fresh directory with Python and `cryptography`:

```sh
python3 language-packs/make_lookup_fixture.py NEW/signed-lookup.json
python3 language-packs/make_bilingual_fixture.py NEW/bilingual-lookup.json
```

Each invocation creates an ephemeral P-256 key in memory. Private key material is
never persisted. Signatures differ on regeneration; the public output and its
provenance must be updated together. The fixture dictionary examples and native
boundary assertions remain those of the existing generators and tests.

The schema-1 integrity/atomic-activation tests create their own tiny SQLite/P-256
inputs natively and retain the public inputs in the test app Documents directory.
None of these tests reads or overwrites a user pack's trusted revision namespace.
