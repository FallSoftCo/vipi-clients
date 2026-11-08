# Signed pack activation qualification

`VocabularyPackStore` has no production download caller or release trust key.
This change implements [the shared activation contract](../../docs/PACK_ACTIVATION.md)
without changing that distribution boundary, the signed pack schemas, or the
64 MiB payload cap.

The encrypted `PrivateRecords` item is the sole authority for both high-water
revision/hash and the active file. It retains the exact original manifest bytes,
their digest, and the detached signature. A legacy receipt does not acquire
trusted metadata from its unsigned JSON pointer: lookup requires a verified
reinstall. Removal retains the high-water mark with an explicit inactive state.

`status()` distinguishes active, inactive, absent and reinstall-required states,
and exposes remaining obsolete files. Installation returns its pack ID after
commit even if cleanup fails. Removal returns its committed status. An optional
cancellation callback is checked before staging and before commit; callers must
supply their own cancellation check. Once committed, cancellation cannot imply
that activation did not occur.

The native test uses small signed synthetic SQLite databases in isolated owned
directories, separate from real account/history or bundled language data:

```
adb -s emulator-5620 shell am instrument -w -r \
  -e class co.fallsoft.vipi.VocabularyPackActivationDeviceTest \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
```

The retained old-source control forces the second `AtomicFile` write to fail
while preserving the previous pointer. Candidate cases cover precommit
cancellation and a real trusted-record write failure, postcommit cleanup
failure, removal and reinstall, legacy metadata rejection, missing/corrupt files,
rollback/conflicting revision/untrusted input, and concurrent store handles.
Each run retains its public synthetic key, exact manifests/signatures/databases,
and receipts. The test-only checkpoint setter rejects non-debug builds.

These are native file-operation failure and reopen checks, not device-power-loss
or interrupted-download evidence. Selected database integrity is verified on
lookup/status in this unconnected installer; production lookup performance and
any immutable-file verification cache need separate qualification. The current
bundled conversation lookup path is unchanged.
