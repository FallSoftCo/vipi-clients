# Apple build 2 source supplement — source preview

This candidate patch changes only `ios/project.yml` from build number 1 to 2. The base is the archive in the [v3 source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17-v3), SHA-256 `3d3884ea4cc4632fa5f137deba816b386edccf5a6d00edde77b93ca2bcae304c`. The source inputs have been reconciled with the locally verified signed Apple 1.0 (2) IPA. This supplement does not imply an App Store upload or customer release.

In an extracted, writable copy of that archive, check the exact baseline and apply from the source root:

```sh
printf '%s  %s\n' 995a42d643e608ca7b9928e18eb656dc07c5d19ffc1868054e150b15364c1112 ios/project.yml | sha256sum -c -
patch --batch --forward -p1 < /path/to/build-number.patch
printf '%s  %s\n' 69407b73a8eafa8fe0a5f7e79018c75b0744babc3789cdc5f14af50cfa8665e9 ios/project.yml | sha256sum -c -
```

The patch SHA-256 is `ed1fe5891d67c040ab4336a9bd758c421c2170172f8b2a73d1721398e93c8af6`. Application to an exact base was tested successfully. The two retained Apple build input manifests match across all 419 listed entries. Of these, 417 match the published base, `ios/project.yml` is covered by this patch, and `ios/BUILDING.md` is build documentation excluded from the public archive; `CLIENT_SOURCE.md` provides public instructions. Three shared utilities differ across the diverged revisions but were not listed as frozen Apple compilation inputs: one regenerates the retained speech data, one checks source assets, and one packages source. The Apple packaging step verifies and copies the retained speech data. The signed IPA was locally verified; see the accompanying receipt for its hash and scope.

The corrected archive used an isolated local LibSignalClient package path to avoid an Xcode package-identity collision. The retained comparison records 221 byte-identical files at the pinned library revision; this changes generated project references, not library source. Xcode also marked 53 localization entries stale in source metadata after the original input snapshot, with no key or localized-value changes. All 13 compiled localization files matched the unsigned build; the timing of the metadata write is not established. The local IPA qualification passed without an upload.
