# Apple build 2 source supplement — unpublished

This candidate patch changes only `ios/project.yml` from build number 1 to 2. The base is the archive in the [v3 source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17-v3), SHA-256 `3d3884ea4cc4632fa5f137deba816b386edccf5a6d00edde77b93ca2bcae304c`. The patch is not yet published and must not be represented as corresponding to a signed artifact until that artifact's actual inputs have been verified.

In an extracted, writable copy of that archive, check the exact baseline and apply from the source root:

```sh
printf '%s  %s\n' 995a42d643e608ca7b9928e18eb656dc07c5d19ffc1868054e150b15364c1112 ios/project.yml | sha256sum -c -
patch --batch --forward -p1 < /path/to/build-number.patch
printf '%s  %s\n' 69407b73a8eafa8fe0a5f7e79018c75b0744babc3789cdc5f14af50cfa8665e9 ios/project.yml | sha256sum -c -
```

The patch SHA-256 is `ed1fe5891d67c040ab4336a9bd758c421c2170172f8b2a73d1721398e93c8af6`. Application to an exact base was tested successfully. The compared revisions diverge: three exported shared build/source-check utilities differ outside `ios/`, as identified in the receipt. They are not represented as byte-identical; verify actual final build inputs before asserting complete correspondence. Signing and export configuration is separate and remains unverified.
