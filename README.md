# Vipi client source

Vipi is a native messaging app that introduces another language through everyday chats. Selected words alternate in place, with local reading guides and speech.

The [November 16 source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-16) contains the Android and Apple client source, bundled language data, build tools, dependency notices and retained upstream sources. Build instructions are in `CLIENT_SOURCE.md` inside the archive. `SOURCE_MANIFEST.json` records each included file and its checksum.

This is pre-release source. Store distribution, signing, billing and background-delivery qualification are still in progress. Automatic immersion uses accepted local mappings; the package does not establish complete conversational coverage or pronunciation accuracy.

The client code is licensed under AGPL-3.0-only. Third-party libraries, dictionaries and voices retain their own licenses and notices, included in the archive. Build dependencies fetched separately, including translation SDKs, retain their own terms. Source availability does not settle every combined-binary distribution question.

The source archive SHA-256 is:

```text
b6e34c24befaf58232ff7b78e39f71478e555bbf18c535dbc9810831c3edcead
```

The package is frozen at source revision `dbe2cfbb91c6064fb0e24a3c01e2e1ef928e536d`. Its recorded application inputs match the Android build at `0fda43f5067e4bb3e339eacfb68d3b7f3bc4bce1` and the unsigned Apple build at `4908d4e7c9d98d8a33547f52883961108f457547`. Those revision identifiers refer to the preserved development history; this repository provides the source snapshot as a release asset.

Vipi is developed by Fallible Software, Co. [Product information and contact](https://api.mambovipi.app/help).
