# Vipi

Vipi is free, encrypted chat with friends. A word from your conversation appears in the language you’re learning. Tap the message to hear the practice words, or hold to read the original.

**The incremental chat release is in testing.** Both store reviews were withdrawn. Vipi uses the shared Fallsoft sign-in. Deleting a Vipi profile preserves the shared account. The global Fallsoft deletion flow remains disabled pending coverage of all affected apps.

- [Product and experience](docs/PRODUCT.md)
- [Incremental immersion and free chat](docs/INCREMENTAL_IMMERSION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation and release gates](docs/IMPLEMENTATION.md)
- [Verification ledger](docs/VERIFICATION.md)
- [Decisions and environment receipts](docs/DECISIONS.md)

Swift/SwiftUI for iOS and Kotlin/Compose for Android. Each platform owns word selection, local translation, live transliteration, speech, storage and navigation. An eligible message introduces at most one new word and can repeat earlier words. Translation uses existing on-device provider APIs only. Shared artifacts are schemas, licensed transliteration data and behavioral fixtures; there is no custom shared application engine.

Current source authority (November 7, 2026): `/home/ai/Development/vipi-production-20261107`, branch `delivery/production-20261107`. Git history, previously uncommitted source and newer native changes were reconciled during recovery. The older `/home/ai/Development/vipi` directory is not authoritative. OZZZ-OS and the dedicated GPU host have been retired; do not use historical commands that reconnect to them.

The live relay runs on consolidated `fallsoft-production-20261106`. New Apple development uses native `apple@macbook-pro`; the previous development VM was preserved and retired on November 9 and must not be recreated. Android reuses its existing QA emulator. Preserve unrelated work. See [current environment receipts](docs/BUILD_ENVIRONMENTS.md) for source mirrors, build results and host authority.

No credentials, signing material, customer content, or provider tokens belong in this repository.
