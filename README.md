# Vipi

Native private messaging that helps people acquire another language through conversations that matter to them.

**Status: restricted staging is live; not ready for public customers or store submission.** This is a new product, separate from Enterprise OZZZ and the earlier Osmos applications. Do not reuse their production databases, accounts, identifiers, or services. See [current delivery status](docs/DELIVERY_STATUS.md) for qualified behavior and remaining gates.

- [Product and experience](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation and release gates](docs/IMPLEMENTATION.md)
- [Verification ledger](docs/VERIFICATION.md)
- [Decisions and environment receipts](docs/DECISIONS.md)

Swift/SwiftUI for iOS and Kotlin/Compose for Android. Each platform owns its local translation, vocabulary alignment, speech, storage, and navigation. Shared artifacts are schemas, language data, and behavioral fixtures, not a custom shared application engine.

Current source authority (November 7, 2026): `/home/ai/Development/vipi-production-20261107`, branch `delivery/production-20261107`. Git history, previously uncommitted source and newer native changes were reconciled during recovery. The older `/home/ai/Development/vipi` directory is not authoritative. OZZZ-OS and the dedicated GPU host have been retired; do not use historical commands that reconnect to them.

The live relay runs on consolidated `fallsoft-production-20261106`. New Apple development uses native `apple@macbook-pro`; the previous development VM was preserved and retired on November 9 and must not be recreated. Android reuses its existing QA emulator. Preserve unrelated work. See [current environment receipts](docs/BUILD_ENVIRONMENTS.md) for source mirrors, build results and host authority.

No credentials, signing material, customer content, or provider tokens belong in this repository.
