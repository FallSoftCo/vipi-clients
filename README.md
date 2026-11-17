# Vipi client source

Vipi is a native messaging app that introduces another language through everyday chats with friends. Selected words alternate in place, with local reading guides and speech.

The [November 17 source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17) contains Android and Apple client source, bundled language data, build tools, dependency notices and retained upstream sources. It includes the reviewed cardless-access, localization, accessibility and backup-recovery changes. Build instructions are in `CLIENT_SOURCE.md` inside the archive; `SOURCE_MANIFEST.json` records each included file and its checksum. Inactive language experiments and private account-state diagnostics are excluded.

This is pre-release source. Store distribution, signing and remaining release qualification are still in progress. Automatic immersion uses accepted local mappings; the package does not establish complete conversational coverage or pronunciation accuracy.

The client code is licensed under AGPL-3.0-only. Third-party libraries, dictionaries and voices retain their own licenses and notices, included in the archive. Build dependencies fetched separately, including translation SDKs, retain their own terms. Source availability does not settle every combined-binary distribution question.

The current source archive SHA-256 is:

```text
dc1045360dd1550c9e53bae4ff6809e15cc26a10fd33d6e27f8413bba9b4fef2
```

The package is frozen at source revision `a547a4db1cba696027613543e17cce1e55a119aa`. Recorded application inputs match Android version 2 (1.0.1) at `195c952` and the unsigned, CocoaPods-integrated Apple Simulator build at `7dd2929`. Simulator verification does not establish device-only translation or signed Apple build identity. These revision identifiers refer to the preserved development history; this repository provides the source snapshot as a release asset.

The [November 16 preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-16) remains available for the earlier version 1 inputs.

Vipi is developed by Fallible Software, Co. [Product information and contact](https://api.mambovipi.app/help).
