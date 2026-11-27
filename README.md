# Vipi

Vipi is free, encrypted chat with friends. Use **Immersion** in the chat header to learn one new word at a time or read full messages in the language you’re learning. Tap a message to listen and follow the word highlight. Hold to read the original.

**The free chat release is in testing.** The November 24 store submissions are closed. Vipi uses the shared FallSoft sign-in. Deleting a Vipi profile preserves the shared account. The global FallSoft deletion flow remains disabled pending coverage of all affected apps.

- [Product and experience](docs/PRODUCT.md)
- [Incremental immersion and free chat](docs/INCREMENTAL_IMMERSION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation and release gates](docs/IMPLEMENTATION.md)
- [Verification ledger](docs/VERIFICATION.md)
- [Contributing locally and running checks](CONTRIBUTING.md)
- [Maintaining the apps, relay and website](docs/MAINTAINING_VIPI.md)
- [Human release runbook](docs/HUMAN_RELEASE.md)
- [Decisions and environment receipts](docs/DECISIONS.md)

Swift/SwiftUI for iOS and Kotlin/Compose for Android. Each platform owns word selection, local translation, live transliteration, speech, storage and navigation. In one-word mode, an eligible message introduces at most one new word and can repeat earlier words. Translation uses existing on-device provider APIs only. Shared artifacts are schemas, licensed transliteration data and behavioral fixtures; there is no custom shared application engine.

This launch branch builds on the November 24 store source and integrates the tested free relay changes. Use its Git commit and signed artifact hashes to identify a candidate. The November 7 delivery checkout and the recovered worktrees contain historical revisions. OZZZ-OS and the dedicated GPU host have been retired.

The live relay runs on consolidated `fallsoft-production-20261106`. New Apple development uses native `apple@macbook-pro`; the previous development VM was preserved and retired on November 9 and must not be recreated. Android reuses its existing QA emulator. Preserve unrelated work. See [current environment receipts](docs/BUILD_ENVIRONMENTS.md) for source mirrors, build results and host authority.

No credentials, signing material, customer content, or provider tokens belong in this repository.
