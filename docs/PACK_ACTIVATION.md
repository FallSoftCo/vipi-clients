# Signed pack activation contract

This November 8 qualification fixes the existing native `VocabularyPackStore`
commit boundary. It does not enable a network updater, add a production signing
key, promote research language data, or change the 64 MiB payload limit.
The shipped conversation path currently uses app-bundled catalogs. Provider
translation-model downloads are a separate Apple/ML Kit operation.

## One authoritative activation record

Stage the database in the store's owned directory, validate the original signed
manifest and payload with the existing signature, size, hash, schema and policy
checks, and finalize the immutable revision file before activation. Preserve
the exact manifest identity in the new record; do not reconstruct signature
input from a decoded JSON object. Retain the native file synchronization and
atomic replacement guarantees, and state the boundary actually exercised by QA.

One atomic trusted-record update must contain both the accepted high-water
revision/hash and the active manifest/filename, or an explicit inactive state.
Use the existing Keychain item on Apple and authenticated `PrivateRecords`
record on Android. A separate filesystem JSON pointer is not authoritative.
Keep the record within the existing native record bounds. Names remain derived
from the validated language pair, revision and lowercase payload hash.

Serialize install, lookup and removal for the same store namespace, including
multiple in-process handles. Recheck the accepted revision inside that boundary.
Do not allow a later finishing older install to replace a newer accepted pack.
Existing locks/actors and native primitives are sufficient; no shared runtime
or service is required.

The activation record is the commit point:

- Any validation, staging, cancellation or trusted-record failure before commit
  leaves the previously active pack readable and its high-water mark unchanged.
- Once the record commits, lookup resolves the new immutable file directly.
  A postcommit obsolete-file cleanup failure cannot make activation fail or
  restore an older revision. Preserve the active file and defer owned cleanup.
- Cancellation is observed before commit. Do not report a postcommit cancellation
  as if activation had not happened. Return or recover the committed state.
- Removal first atomically marks the pack inactive while retaining its accepted
  revision/hash, then removes owned files. Lookup cannot silently reactivate a
  leftover file. Deletion failures must remain observable to the storage manager;
  a failed removal must not claim that disk space was reclaimed.
- Reinstallation of the same revision and hash remains permitted, including
  after removal or missing-file recovery. Lower revisions and same-revision
  conflicting hashes remain rejected. A missing/corrupt active file must never
  cause automatic fallback to an older version.

The record protects against stale signed update replay within the existing
application storage model. It is not a new claim of hardware monotonic storage,
protection against a compromised device, or tested device-power-loss durability.

## Legacy QA records

The old record retains only revision and payload hash; its separate JSON pointer
does not retain the original signed manifest/signature. There are no production
callers of this installer. Preserve those legacy files and high-water marks,
but do not infer newly trusted manifest metadata from the unsigned pointer.
Return an explicit reinstall-needed state for legacy lookup. A normal verified
same-revision/same-hash or newer install upgrades the record atomically. Never
reset the revision to make migration pass, silently delete legacy records, or
trust a key delivered alongside the pack.

## Bounded native qualification

Use a small signed synthetic fixture and the current native store. Demonstrate
the old receipt/pointer failure before the correction where practical, retaining
its result. After the change exercise:

1. Initial install and upgrade with a newly opened store reading the active pack.
2. Failure/cancellation after staging but before record commit: the old pack
   remains readable, the high-water mark is unchanged, and retry succeeds.
3. Postcommit cleanup failure: the new pack remains readable after reopening.
4. Removal with cleanup failure: inactive lookup, retained high-water mark and
   honest leftover-file status; exact reinstall succeeds and rollback fails.
5. Legacy high-water preservation and verified reinstall, including rejecting a
   fabricated legacy pointer as migration authority.
6. Concurrent handles cannot downgrade or remove a newly accepted active file;
   tampered/untrusted input and same-revision conflicts still fail closed.

Retain exact source/build/input hashes and distinguish injected failures from
an actual process termination. These checks qualify atomic activation only;
download interruption, production trust distribution, user storage controls,
language meaning and store readiness remain separate gates.
