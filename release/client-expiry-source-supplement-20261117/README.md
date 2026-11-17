# Android 1.0.3 (4) and Apple 1.0 (3) source supplement

This patch adds a clear, localized message when a sign-in attempt expires and advances the client build numbers. It covers 18 files and applies directly to the original [v3 source archive](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17-v3). Start from that archive, without applying the separate Apple build 2 supplement first.

The base archive SHA-256 is `3d3884ea4cc4632fa5f137deba816b386edccf5a6d00edde77b93ca2bcae304c`. The patch SHA-256 is `e1954eade90e7a10c966f1d5b58bdd933894813a73556a08ebd7f7df9fdf05f8`. The accompanying receipt lists each changed file's original and resulting hashes; a null original hash identifies a new file.

After checking the archive and patch hashes, extract the archive to a new writable directory. From its source root, run:

```sh
patch --dry-run --batch --forward -p1 < /path/to/client-expiry-source.patch
patch --batch --forward -p1 < /path/to/client-expiry-source.patch
```

All changed baseline files were compared against the actual published archive. Patch application was checked, and every resulting file matched its platform's frozen source: Android `4cc7f95c18e7284e37d4b0505eb771875d0a8c0d`, Apple `decc33d25accdc0f2cb0bf8a2bac290697695f8c`. Dependencies and bundled language data are unchanged from the base source. Build instructions and dependency notices remain in the archive.

This is a source supplement, not an app distribution or a statement of store approval. Platform artifact and runtime qualification are recorded separately. The Apple build uses the same pinned local LibSignalClient sources through an isolated package path, as documented in the earlier supplement; generated project paths are machine-specific.
