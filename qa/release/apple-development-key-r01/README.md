# Native development signing qualification

The native Mac successfully used the company Apple Development identity to generate and discard a cryptographic signature for the previously compiled Vipi device app. The interactive Terminal probe exited 0 in 2.65 seconds; the app binary remained unchanged. The owned Terminal window was closed after completion. No keychain ACL, password or distribution-key access changed.

The matching development profile is installed for the attached iPad and explicit `co.fallsoft.vipi` identifier. Its included certificate expires November 30, 2026; the profile’s later expiry does not extend that certificate. Device installation and execution are separate pending checks.

This is a development-key qualification, not an App Store signature or export. The separate distribution identity remains blocked by its locked keychain. The tested unsigned binary predates the current starter changes; no current-source execution claim follows. See `receipt.json` and `release/apple-store-configuration.json`.
