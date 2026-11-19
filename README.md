# Vipi

Vipi: immersive chat with friends. Messages appear in the language you are learning; hold to see the meaning and tap to listen.

**Status: the full-message immersion update is in qualification; both store reviews are withdrawn.** Vipi uses the shared Fallsoft sign-in with its own app data, subscriptions and encrypted messages. Vipi-only deletion preserves the shared account; global Fallsoft deletion remains disabled until all affected apps are covered. Preserve the databases and services of Enterprise OZZZ and Osmos. See [current delivery status](docs/DELIVERY_STATUS.md) for qualified behavior and remaining work.

- [Product and experience](docs/PRODUCT.md)
- [Current full-message immersion contract](docs/FULL_MESSAGE_IMMERSION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation and release gates](docs/IMPLEMENTATION.md)
- [Verification ledger](docs/VERIFICATION.md)
- [Decisions and environment receipts](docs/DECISIONS.md)

Swift/SwiftUI for iOS and Kotlin/Compose for Android. Each platform owns its full-message translation, live transliteration, speech, storage and navigation. Translation uses existing on-device provider APIs only. Shared artifacts are schemas, licensed transliteration data and behavioral fixtures; there is no custom shared application engine.

Current source authority (November 7, 2026): `/home/ai/Development/vipi-production-20261107`, branch `delivery/production-20261107`. Git history, previously uncommitted source and newer native changes were reconciled during recovery. The older `/home/ai/Development/vipi` directory is not authoritative. OZZZ-OS and the dedicated GPU host have been retired; do not use historical commands that reconnect to them.

The live relay runs on consolidated `fallsoft-production-20261106`. New Apple development uses native `apple@macbook-pro`; the previous development VM was preserved and retired on November 9 and must not be recreated. Android reuses its existing QA emulator. Preserve unrelated work. See [current environment receipts](docs/BUILD_ENVIRONMENTS.md) for source mirrors, build results and host authority.

No credentials, signing material, customer content, or provider tokens belong in this repository.
