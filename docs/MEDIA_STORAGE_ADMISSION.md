# Shared storage for encrypted attachments

The media relay uses the existing `20261121_04` schema. Existing clients keep their upload IDs, authenticated routes, retry behavior and ciphertext digests. The two regular clients have exchanged encrypted voice notes through an isolated relay.

A new upload reserves its declared bytes and one object in PostgreSQL before the request succeeds. All API workers serialize these decisions with the same transaction-scoped advisory lock. Ready and unfinished reservations count even when their expiry timestamp has passed. Cancellation and expiry transfer the charge to the cleanup intent until the worker can unlink the files and fsync their directory. An account deletion can remove the original size. Each such pending intent counts as one object at the historical hard maximum of 67,108,892 bytes until deletion finishes.

The PUT checks the filesystem headroom again and preallocates the entire private file before consuming the HTTP body. The headroom test conservatively charges all unfinished declarations and block rounding even when another writer has already allocated some space. Existing files and other services’ usage reduce the free-space reading. File locks defer cleanup for open readers or writers. Each retry removes abandoned parts of the same blob after checking its original lease. A finalized upload with the original length and hash can be recovered after an interrupted SQL commit. Space denials leave the original reservation eligible for an explicit retry.

| Setting | Development default |
| --- | ---: |
| `VIPI_MEDIA_GLOBAL_BYTES` | 1,073,741,824 bytes |
| `VIPI_MEDIA_GLOBAL_BLOBS` | 8,192 blobs |
| `VIPI_MEDIA_MIN_FREE_BYTES` | 1,073,741,824 bytes |
| `VIPI_MEDIA_MIN_FREE_INODES` | 1,024 inodes |

A logical byte or count denial returns HTTP 429 with `media_storage_full`. A disk or inode floor breach, missing expected volume, unsupported preallocation or allocation failure from an exhausted filesystem/quota returns HTTP 507 with `media_storage_unavailable`. Stalled transfers still occupy one of the existing per-worker transfer slots.

## Deployment and recovery

Use identical budgets and the same private mounted directory for every API and expiry worker. Staging and production require an existing directory and a configured `VIPI_MEDIA_VOLUME_ID` matching the administrator-provisioned `.vipi-volume-id` file. Each process verifies that marker and its opened directory identity. Give both service identities scoped write access. Verify file locking, allocation, atomic rename and directory fsync on the target Linux filesystem. A filesystem/project quota or dedicated bounded volume and a host reserve protect other workloads when unrelated writers consume space after admission. Choose these values from measured shared-host requirements.

Before enabling, reconcile the database and volume together. Existing valid upload/ready rows are counted immediately. Inventory unmatched files and old duplicates from previous binaries, retain their evidence, and resolve them before accepting new data. Existing physical files still reduce the filesystem free-space reading. All writers and cleanup processes must adopt the shared rules together. Keep a matched database/volume recovery point and preserve the marker through a coordinated restore. A rollback to a binary without this admission logic requires draining new media work and resolving outstanding reservations first.

Each admission reads the blob table and the cleanup queue. The expiry worker processes batches of 100 and retires eligible tombstones seven days after expiry once cleanup completes. The global object cap bounds charged objects. Retained tombstones and delayed maintenance can enlarge the table independently. With 256 live rows and 40 cleanup intents, local PostgreSQL query timings were 0.39 ms with 64 historical rows, 1.83 ms with 8,192, and 11.27 ms with 65,536. Retry/cleanup also enumerates the flat volume directory for old token-named parts. Measure against the intended history, backlog, worker count, text latency and storage before a shared-host rollout.
