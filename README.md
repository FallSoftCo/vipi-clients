# Vipi

Native private messaging that helps people acquire another language through conversations that matter to them.

**Status: implementation in progress; not ready for deployment or store submission.** This is a new product, separate from Enterprise OZZZ and the earlier Osmos applications. Do not reuse their production databases, accounts, identifiers, or services.

- [Product and experience](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation and release gates](docs/IMPLEMENTATION.md)
- [Verification ledger](docs/VERIFICATION.md)
- [Decisions and environment receipts](docs/DECISIONS.md)

Swift/SwiftUI for iOS and Kotlin/Compose for Android. Each platform owns its local translation, vocabulary alignment, speech, storage, and navigation. Shared artifacts are schemas, language data, and behavioral fixtures, not a custom shared application engine.

Source authoring mirror: `/home/ai/Development/vipi`. New canonical development/build workspace: `/aosp/development/vipi` on `OZZZ-OS`; iOS build workspace on the existing Mac. No previous repository is being cut over. Keep source mirrors explicitly synchronized and record hashes before release builds. Dependency installation and substantial Linux builds run on OZZZ-OS with `storage-build`; iOS builds run on the authorized Mac environment.

No credentials, signing material, customer content, or provider tokens belong in this repository.
