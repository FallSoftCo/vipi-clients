# Vipi

Native private messaging that helps people acquire another language through conversations that matter to them.

**Status: implementation in progress; not ready for deployment or store submission.** This is a new product, separate from Enterprise OZZZ and the earlier Osmos applications. Do not reuse their production databases, accounts, identifiers, or services.

- [Product and experience](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation and release gates](docs/IMPLEMENTATION.md)
- [Verification ledger](docs/VERIFICATION.md)
- [Decisions and environment receipts](docs/DECISIONS.md)

Swift/SwiftUI for iOS and Kotlin/Compose for Android. Each platform owns its local translation, vocabulary alignment, speech, storage, and navigation. Shared artifacts are schemas, language data, and behavioral fixtures, not a custom shared application engine.

Current source authority (November 7, 2026): `/home/ai/Development/vipi-production-20261107`, branch `delivery/production-20261107`. Git history, previously uncommitted source and newer native changes were reconciled during recovery. The older `/home/ai/Development/vipi` directory is not authoritative. OZZZ-OS and the dedicated GPU host have been retired; do not use historical commands that reconnect to them.

The live relay runs on consolidated `fallsoft-production-20261106`. Apple development uses the existing `ozzz-development-20261021` VM on the MacBook, user `lume`; the native Mac is its controller. Android uses the existing QA emulator. Reuse these environments and preserve unrelated work. See [current environment receipts](docs/BUILD_ENVIRONMENTS.md) and the November 7 checkpoint in [verification](docs/VERIFICATION.md).

No credentials, signing material, customer content, or provider tokens belong in this repository.
