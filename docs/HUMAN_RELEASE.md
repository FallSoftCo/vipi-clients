# Vipi release runbook

Use this runbook to build, qualify, deploy and submit a Vipi release. Every
decision and external action belongs to you as the authenticated owner. Use
the native tools, store consoles and reviewed command-line scripts from the
links below. Record the result in the release record before moving on.

## Start with the source and the current systems

The [maintenance guide](MAINTAINING_VIPI.md) identifies the private product,
infrastructure and marketing sources. Verify the current Git commit and tree
for each component you plan to change. Use a clean worktree for the release.
Keep older exports, test APKs, archives, intermediate deployment files and
device installations tied to their original receipts.

```sh
git status --short
git rev-parse HEAD
git rev-parse HEAD^{tree}
git diff --check
```

Start a private release record before the first external action. Include the
human release owner, UTC time, intended environment, Git revisions,
application IDs and versions, artifact paths and SHA-256 digests. Include the
store track, eligible testers and devices, test accounts, and the exact scope
of any server change. Use references to approved secret storage and redacted
account labels. Keep credentials, messages, device tokens, and customer
information out of the record.

Read the current deployment, store tracks, build history, active review,
release settings and publishing queue. Previous work may already have
uploaded or distributed the same build. A Git commit, local export,
automated test, or screenshot of an upload button does not establish what the
store or host accepted.

## Read the last verified launch state

On 2026-11-27, the private handset run exercised both operating systems using
a private relay. It covered direct chat, groups, reply, reaction, link preview
and direct attachments under synthetic accounts. Read the original device
record before using it as acceptance for a later revision.

- The current production database had reached `20261126_01`. The public
  serving origins were healthy. Production admission for the new chat
  capabilities and ciphertext storage remained closed. Use the independent
  host readback and dated [relay deployment guide](MAINTAINING_VIPI.md#operate-the-website-studio-and-relay)
  to establish current state.
- iOS build 11 had a verified local distribution archive. Android version
  1.0.33 (34) had a verified local upload-key artifact. Read the actual
  consoles to establish the current uploaded and privately distributed
  builds. Store-distributed, cross-platform production sign-in, messaging and
  visible push on both handsets remain separate acceptance checks.
- The owner release runbooks and local maintenance authentication tools
  were reviewed offline. Shared host credential enrollment and the live
  proof of the human receiver are tracked in the deployment section below.

## Run the release as one operator

| Step | Evidence needed to move on |
| --- | --- |
| Source selection and signed build | Exact clean revision, matching resources and notices, signer, version and artifact digest. Follow the [Android guide](ANDROID_MAINTAINER.md) or [iOS guide](IOS_MAINTAINER.md). |
| Private and production acceptance | Named hardware and builds, approved test accounts, relay and push environment, results by scenario, and any remaining limitations. |
| Production relay and storage | Current state, reviewed scope and recovery, authenticated affected owners, exact deployment receipts, and independent post-check. |
| Privacy, product copy and store listings | Current legal URLs and statements, access to the listing, supported features and device/OS claims matched to actual acceptance. |
| Store review and rollout | Internal track and review readback, correct signed artifact, manually verified release settings and an auditable result for each action. |

A single person can build, verify, approve and publish Vipi with the accounts
and host roles they own. Record distinct test identities on two devices. Verify
the deployed state from the documented independent admin route and preserve its
output. For a shared-host change, also check the scope and current constraints
of other workloads. Record any ownership you do not hold before starting a
change that would affect it.

Use the [access checklist](RELEASE_ACCESS.md) before a release window and when
a session or signing credential needs refresh.

## Qualify what users will run

1. Run the existing suites at the exact candidate. Archive the result
   bundles with toolchain versions and revision. The [verification
   ledger](VERIFICATION.md) and each platform guide explain the available
   suites and what they exercise.
2. Use owned test accounts and approved test devices. Before sign-in, check
   the app's identity authority and the account's current device binding.
   A successful fresh sign-in can register a device. Preserve existing
   primary devices, reviewer accounts, local encrypted history and accepted
   messages. Confirm any intended provisioning or transfer in the release
   record before starting that test.
3. Install the intended build through its private distribution track. Record
   the installed version, app ID and delivery channel on each handset. On
   Android, verify the Play app-signing certificate and verified link routing.
   On iOS, verify the TestFlight build and production APNs entitlement.
   Development signing, local sideloading and internal app sharing each
   exercise a different installation path.
4. Run the two-device checklist below. Use disposable test content, addresses
   and files. Record outcomes and delivery timing with redacted identifiers.
   For sensitive captures, retain only the information needed to verify the
   result.
5. Record remaining failures or unavailable cases. Keep release eligibility
   tied to the claimed features and supported OS and device matrix.

| Scenario | Check on the actual devices |
| --- | --- |
| Sign-in and links | Complete the approved sign-in path, open a valid friend link, and return to the intended signed-in device and account. Check ordinary background and foreground return. |
| Direct chat | Send and receive on both operating systems. Check delivery/read status, reconnect and duplicate handling. Exercise reply, reaction, link preview, hold to reveal original, and speech in supported languages. |
| Group chat | Verify a real invite, membership, text, reply, reaction and link preview. Remove a test member and verify access and delivery stop as intended. |
| Direct attachments | Open gallery and camera, send and receive a disposable photo, record and send audio, check playback and interruption. Verify outcomes after a short network loss. |
| Push | Use locked hardware with the intended notification settings. Verify arrival, preview privacy, routing after tapping, and recovery after a restart. Check both operating systems and distinguish a provider receipt from a visible notification. |
| Account and history | Verify restore, device replacement, blocking and deletion with dedicated disposable accounts. Confirm retained encrypted history and the current app-only deletion boundary. |

Keep private-relay proof and production proof in the release record. A paired
private hardware run verifies native behavior and relay compatibility under
its fixture. Production delivery requires the current public relay, its
production-capable push path and both intended store-distributed builds. The
current feature scope includes attachments in direct conversations and text
and supported chat actions in groups.

## Deploy through the human host workflow

Use the [human authorization guide](https://github.com/FallSoftCo/infrastructure/tree/cd703a20399587bae8e1fcbacc310dfad682349a/services/vipi-relay/ops/human-maintenance)
with the [deployment and recovery runbooks](MAINTAINING_VIPI.md#operate-the-website-studio-and-relay).
The local command can sign an exact maintenance request with the personal key
already loaded in your SSH agent and return an authenticated review receipt.
The production gate also needs the enrolled human key and roster, a reviewed
host receiver, and verified execution receipts. Confirm these are installed
and approved for the exact change before a live operation. The [receiver rehearsal](https://github.com/FallSoftCo/infrastructure/blob/7d251cc8d884df2902b143aefd9e80c5ed63bef0/services/vipi-relay/ops/human-maintenance/RECEIVER-FIXTURE.md)
exercises a signed one-owner lifecycle and recovery in a disposable environment.
The historical Codex-session wrapper records the previous operating path.

Record the current public methods and their serving owners, accepted
operations, database schema, queued background work, capacity, and recovery
path. Review how existing clients and both process generations handle work
around the route switch. Keep database, storage, notification and provider
ownership explicit. Preserve current user data and accepted effects.

Verify the artifact and plan against the approved hashes and current host.
Use the owner's documented sequence and retain the original intent and
result. If a connection drops or a command returns an ambiguous outcome,
inspect the original job, receipt and actual current state. Reconcile those
before any new action. A schema migration may require forward recovery with a
compatible runtime. Use the reviewed recovery for the observed schema and
data, including any effects already accepted by the new generation.

Run the approved postchecks independently. Record current serving versions,
actual routes, health, shared-host limits, expected historical responses and
the behavior of the changed feature. Run production hardware QA after the
feature is actually admitted.

## Distribute, review and publish

1. Read the correct app and account in each console. Confirm the exact
   candidate version and digest, current track state, eligible test group,
   and any pending review or unrelated changes. Record the pre-action state.
2. Upload or select the exact signed internal build. Verify the resulting
   upload record, processing state and track membership. An interrupted
   upload requires a store readback before another upload. A completed
   upload and a tester's installation are distinct events.
3. Complete the hardware checks on the privately distributed builds.
   Review support and privacy URLs, data declarations, screenshot text,
   supported features, enrollment and reviewer access against the observed
   production behavior. Keep original successful and failed results.
4. A human publisher submits the intended version only after all applicable
   release checks pass. Verify the review identifier, submitted artifact,
   track and release option afterwards. Stop and reconcile a pending or
   uncertain submission before taking any review action.
5. A human publisher controls the release date and rollout. Verify that the
   console change includes only the intended release. Record resulting
   availability and check production delivery, push and support. If a failure
   emerges, use the exact store pause or reviewed host recovery for that
   release and preserve accepted work.

Use [Apple's internal TestFlight instructions](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers)
and [Google's internal testing instructions](https://support.google.com/googleplay/android-developer/answer/9845334)
alongside the platform-specific runbooks. Google
[internal app sharing](https://support.google.com/googleplay/android-developer/answer/9844679)
uses a separate test signing certificate.
