# Current delivery status

Updated November 18, 2026. **Both store reviews are withdrawn and neither new
app is released.** Full-message immersion is still being qualified. Do not
resubmit or release until that work is complete. Completed uploads, withdrawals,
auth exchanges and Bot requests must not be replayed.

## Current release hold

- Google 1.0.7 (8): 24 changes not yet submitted, zero in review and zero ready
  to publish. Managed publishing remains on.
- Apple 1.0 (5): Developer Rejected; all five submission items were removed,
  with zero active review submissions. The build remains valid and release is manual.
- These are the previously verified November 18 withdrawal results, reconciled
  in [the hold summary](../release/store-review-hold-20261118.json). This document
  update did not inspect the consoles again or perform any store action.

## Current implementation and qualification

Every sent and received message uses full local translation. The default reading
uses transliteration; tapping plays practice-language audio, holding reveals the
meaning in the known language, and double-tapping changes script. The authored
message remains separate from its translated display. The older word-switching
builds and evidence below do not qualify this replacement.

Immersion uses existing on-device APIs only. Apple Translation and Google ML Kit
remain the implementations, including the existing Swahili path. Separate model
experiments have stopped. Tests of Apple Intelligence API variants are research
evidence; they do not establish that the shipping app uses an explicit strategy
or that translations are consistently accurate.

Android's targeted Friend and vBot journeys have passed on the existing emulator;
pronunciation-cache migration and older-OS API compatibility still need closure.
The short landscape capture proves a readable draft and Send control while chat
history is clipped. iOS layout and playback lifecycle work remains in progress,
including large-text settings. Neither platform has a fresh qualified signed
release of the full-message design, and the user's requested phone delivery is
pending that qualification.

The public information pages now describe the full-message design in source.
Their existing invitation and recovery tests pass; that source change has not
been deployed. The prepared store-copy candidates also remain unapplied. Final
assembly must use the qualified native sources and matching copy, then verify
signed artifacts, actual device delivery and store state before submission.

## Historical delivery checkpoint — November 17 to early November 18

Everything below preserves earlier version-specific observations and their
original receipts. In-review states and remaining-work lists below are historical
and are superseded by the current release hold above.

Updated November 17, 2026 (latest handoff observations through November 18,
02:24 UTC). Google **1.0.4 (5)** is in production review. Apple **1.0 (4)**,
both annual subscriptions and both groups are submitted and **Waiting for Review**. Neither
approval nor public availability is established. Completed uploads, review sends,
auth exchanges and Bot requests must not be replayed.

## Latest reconciled state

- Google final **Send** was clicked once at **00:29:54 UTC** on November 18.
  The console reported **24 changes sent for review**; **Changes in review**
  persisted after a fresh reload. At 00:37 UTC the preliminary checks had passed,
  and the console stated that the changes are now in review.
  The submission includes 14 localized listings, four current native screenshots
  and the independently read-back Gamma reviewer credentials.
  See [terminal submission receipt](../release/google-play-review-submission-20261117.json).
  The earlier [v5 draft receipt](../release/android-v5-store-upload-20261117.json)
  records a historical pre-submission checkpoint; its remaining-work list is superseded.
- Android production AAB and matching upload-signed APK were built and verified
  from frozen source **55a9f723f436f4252730c0a85358a9aa32080f8b**.
  AAB SHA-256 is `108e1152a8bf50d93e2d4ab9fd4d464aaf5ca04a9a36a25fc3f6bd0c6383714d`;
  APK SHA-256 is `b49354c1fba8540a5dc1dcc12a281d37b392c64643224de24fdba43d47ebd9fe`.
  Production package/configuration, all four ABIs, signatures, 1,082 assets and
  16 KiB alignment checks passed. See [artifact qualification](../release/android-v5-artifact-qualification-20261117.json)
  and [artifact handoff](../release/android-v5-artifacts-20261117.md).
- Apple **1.0 (4)** was signed and qualified, then delivered once at approximately
  **00:24 UTC** on November 18. IPA size is **431,015,828 bytes**, SHA-256
  `ac1851a2d5947c86552204b1c32ce1f16801dc351d1275b53590ba189b5da416`.
  Strict/deep signature, production push, disabled debugging, 13 localizations
  and source/resource correspondence passed. Processing/export compliance and
  all 13 locale fields are complete; six current public screenshots and exact
  Alpha review credentials were saved. The app, both annual subscriptions and
  both groups were submitted once at **02:22:45 UTC**. All five show **Waiting
  for Review**, verified after reload at **02:24 UTC**. Manual release remains set.
  See [terminal Apple receipt](../release/apple-review-submission-20261117.json).
  Private subscription reference screenshots disclose actual historical build 2
  provenance and typography differences. Artifact/upload qualification remains
  historical; its earlier zero-upload/pending-processing fields are superseded
  by the later terminal receipt without replaying any operation.
- The exact native-redesign source supplement for frozen `55a9f72` was published
  on the existing public v3 source release and anonymously verified. Prior source
  assets remain unchanged. See [terminal publication receipt](../release/native-redesign-source-publication-20261117.json).
  Publication is not a blanket conclusion about every linked dependency's terms.
- The live backend uses shared Fallsoft identity, schema 05, Vipi-only deletion
  and subscription enforcement. Exact verified owner and Gamma identities receive
  complimentary Base/Bot access; other customers retain the ordinary access rules.
  See [shared deployment](../qa/backend/shared-identity-deployment-20261117-r04/deployment.json)
  and [testing-access activation](../qa/backend/owned-testing-access-20261117-r01/deployment.json).
- Fresh Gamma sign-in, normal username setup, device readiness and complimentary
  access passed in the exact production Android v5 APK. One consented vBot prompt
  produced a reply, debited once and displayed **149/150**; independent readback
  found one active device, one settled request, no pending/uncertain requests and
  no purchased entitlements. Word tap and same-word Stop were observed with marked
  Chinese readings. Four current, unedited native frames include the already-delivered
  synthetic friend conversation. See [live review](../qa/ux/android-release-live-20261117-r01/REVIEW.md),
  [receipt](../qa/ux/android-release-live-20261117-r01/receipt.json)
  and [independent service proof](../release/android-v5-owned-review-live-access-20261117.json).
- The user's phone still reported **versionCode 4** in the read-only Termux check
  at **01:55 UTC**. The complete verified v5 APK is in Downloads and its installer
  was opened once; installation is not established. Do not treat the transfer or
  installer opening as a completed update.
- Native chat now offers one-tap word pronunciation, message translation with
  automatic pronunciation, and one translation after a selection-handle release.
  Actual native handle tests passed on both platforms. Android's previously
  missed handle-release request was fixed and its original failure retained.
  See [Android evidence](../qa/immersion/android-native-handles-20261117-r15/README.md)
  and [native UI evidence](../qa/immersion/ui-native-20261117-r13/README.md).
- Arabic source replacements now preserve joined orthographic words. The
  integrated iOS app was visually verified; this does not establish unrestricted
  Arabic reading coverage. See [native rendering](../qa/immersion/arabic-native-ui-20261117-r01/README.md).
- Shared Google public PKCE and the separate native confidential exchange passed.
  The reviewed backend cutover completed once, including schema 05, preserved
  account rows, healthy API/push/timers and unchanged shared services. The real
  HTTPS browser callback then reached the Vipi-only confirmation; Cancel left
  the account intact. See [deployment](../qa/backend/shared-identity-deployment-20261117-r04/deployment.json),
  [confidential exchange](../qa/identity/shared-confidential-native-20261117.json)
  and [browser check](../qa/backend/shared-browser-callback-20261117-r01/native-observation.json).
- Native deletion copy explicitly names Vipi and preserves the shared Fallsoft
  sign-in in all 13 UI locales. Global Fallsoft deletion remains disabled until
  all affected applications are covered. See [copy validation](../qa/identity/vipi-only-deletion-copy-20261117.json).
- Native identity-link manager tests passed. All seven StoreKit lifecycle cases
  now pass on the native macOS test host with unchanged production purchase
  logic; the test waits for asynchronous transaction publication. The earlier
  iOS simulator configuration failure remains recorded. This is separate from
  genuine store transactions. See [StoreKit proof](../qa/identity/storekit-native-host-20261117.json).

## Remaining work and limits

- Observe both stores' review outcomes. Google is in review; Apple's five-item
  submission is Waiting for Review. Do not resend either completed submission.
  Approval and public availability remain unverified; Apple has manual release.
- Earlier Apple builds and their purchase receipts do not establish fresh build 4
  runtime behavior. The private product review notes explicitly disclose the
  historical subscription captures; public listing screenshots are separate.
- Reconcile the phone's pending installer outcome before any further install
  action. Its current known installed version remains 4.
- Preserve the unresolved original company/Beta send and held environments.
  The safe, separate Gamma and owned-peer proofs do not resolve that old outcome.
- Clean-device purchase restore, broader billing lifecycle/provider delivery,
  pronunciation accuracy and unrestricted conversational coverage remain limited
  to their recorded evidence. Actual local/model examples are not universal guarantees.
- Keep the original nine experimental modified files and untracked NLP pilot
  physically preserved and excluded from the committed release source. Regional
  exclusions and dependency-distribution assessments retain their recorded scope.
  Add public store links only after actual public availability is verified.

## Historical narrative — retained, superseded where stated above

The following sections preserve earlier version-specific observations and
uncertainties. Their words “current,” “remaining,” “not submitted” and “not active”
refer to those checkpoints, not the present release. Original receipts remain
immutable; the terminal receipts above determine the current state. An uncertain
external action remains uncertain unless later evidence explicitly resolves it.

## Historical artifact and store checkpoints

Android **1.0.1 (2)**, source `195c952`, was uploaded once, published once to
the existing one-person company test list, and installed through an actual
Google Play update. Installer `com.android.vending`, unchanged data directories
and the retained company account were verified. Play reports 417 MB for a new
install and 1.54 MB for this update. In-place update acceptance establishes
signer continuity; the version 2 certificate was not separately extracted.
See [artifacts](../release/android-build-artifacts-20261117.json) and
[internal release](../release/android-internal-release-20261117.json).

Android **1.0.2 (3)** has signed APK/AAB artifacts from frozen `87d53cd`, with the measured
release-encryption fix, short-message language identification and updated
dependency notices. Its 3,488 tracked Android entries and 655 generated asset
files were checked against the frozen source and retained version 2 manifest.
Signature, bundled model/notices, all 1,082 APK/AAB assets, the JNI keep-name
rule and 16 KiB alignment checks passed. A representative ARM64 download
estimate is 417,879,196 bytes; actual Play distribution may differ. Exact APK
offline smoke passed on a fresh accountless emulator: onboarding, Japanese
Latin/script preview, Swahili, dark theme and access gate. Follow-up confirmed
Full-link scroll reachability and Listen/Stop/idle with Japanese and Swahili
substitutions visible. Audio was disabled: these are UI/controller observations,
not acoustic approval or exact-binary messaging-crypto qualification. Both fresh
test emulators were retired after preserving evidence; original accounts remain.
Version 3 was uploaded once to the Play artifact library and processed. A fresh
reload shows Draft with zero releases, 418 MB for a new install and 2.17 MB for
an update. No track publication or retained-account update occurred.
See [upload receipt](../release/android-v3-store-upload-20261117.json).
See [candidate](../qa/immersion/android-v3-candidate-20261117/candidate.json).

Google's 14 localized listings were field-checked and saved once. Independent
reload verified the locale inventory and English, Swahili and Arabic field
samples. They are ready to send for review, not approved. The existing production draft now references only version 3; its name and all
14 localized release-note payloads were independently reloaded and verified.
Production availability now targets 176 Play region entries, excluding the
France group and China. Both annual plans and their offers show 174 regions
after France removal. The preview shows Ready to release, but no review or
rollout occurred. See [geography](../qa/store-configuration/android-regions-20261117-r01/receipt.json).
See [draft receipt](../release/google-production-v3-draft-20261117.json). Existing artwork declarations and actual
app screenshots remain. See [localization](../release/google-localized-listing-20261117.json).

Apple **1.0 (2)**, source `09056a6`, is now signed with Fallible Software's
Apple Distribution certificate and was delivered once through Transporter at
07:30 America/New_York on November 17. Transporter reported processing finished
at 07:33. Final IPA
SHA-256 is `e0e4e1cc2b7fd2488de1f42d37dae525be50af084949e149c386d7599d72d37a`.
Independent strict/deep signature verification passed, with production push
entitlements and debugging disabled. The 1,019 immersion/lexical/speech resources,
13 privacy manifests and 13 compiled localizations match the checked build.
The prior build 1 and its original upload remain preserved; no upload was repeated.
See [delivery](../release/apple-delivery-build2-20261117-r01.json) and
[verification](../qa/release/apple-signed-build2-20261117-r01/root-verification.json). Fresh App Store Connect
readback now confirms build ID `9367242c-b819-4bc7-9ade-6e192a12c43e`,
The encryption declaration was subsequently saved with standard algorithms
and France No, and build 2 was associated with version 1.0. Its status then
showed Ready to Submit. The internal Vipi Release QA group now contains the
single owned company tester. The supplied TestFlight code was redeemed once,
and build 2 is installed through TestFlight on the native Apple silicon Mac.
Fresh QA sign-in, profile creation, the 30-day access display, both plan prices
and the native invitation share sheet passed. The copied invitation contains
the correct username and its public landing returns HTTP 200. Joining uses the
explicit manual username flow; app-link handoff was not demonstrated.
See [first use](../qa/release/apple-signed-build2-20261117-r01/live-qa-first-launch.json)
and [invitation](../qa/release/apple-signed-build2-20261117-r01/live-qa-invite.json).
The brief earlier login
redirect resolved in the existing session; no reauthentication was needed.
Never repeat the completed upload.

Apple **1.0 (3)** incorporates the expiry-specific sign-in copy and was
independently signed and qualified; its 13 compiled localization catalogs and
resource counts were inspected. The dedicated expiry UI path has not been
exercised on build 3. Transporter delivery and processing were subsequently
recorded, and App Store Connect reload confirmed build 3 attached to the draft.
The attempted Mac update did not establish installation of build 3 and was not
replayed. See [delivery](../qa/release/apple-signed-build3-20261117-r01/upload-processing.json)
and [readback](../qa/release/apple-signed-build3-20261117-r01/asc-update-followup.json).
The expiry source supplement was published separately; it predates the current
redesign. See [publication](../release/client-expiry-source-supplement-20261117/publication-receipt.json)
and [qualification](../qa/release/apple-signed-build3-20261117-r01/qualification.json)
and [source scope](../qa/release/apple-signed-build3-20261117-r01/source-and-scope.json);
their upload=false fields record the earlier pre-upload check.

Reviewed text is saved and reload-verified in all 13 Apple-supported locales.
Swahili is not an ASC locale; new locales retain inherited English keywords and
URLs. The approved English iPhone large and iPad 13-inch screenshot pairs were
uploaded once and each shows 2/10 after reload. The medium iPhone slot uses those
existing assets. These captures show real production views with a synthetic
offline conversation; they do not establish live delivery. Privacy, reviewer
access and manual release are saved. Build association and the encryption questionnaire are complete; purchase
qualification remains incomplete. App and both subscriptions have 173 selected
storefronts, excluding France and mainland China. The app download price is Free.
Subscription prices and trial terms are unchanged. See [configuration](../qa/release/apple-signed-build2-20261117-r01/storefront-and-compliance-configuration.json). No physical iPad was used.
See [Apple configuration](../release/apple-store-configuration.json).

**Signing is authorized.** The user explicitly directed “you must sign” on
November 17. The team completed the proven route: a normal signed Xcode archive
followed by Organizer automatic export and independent final IPA checks.
Directly exporting an unsigned archive previously lost its push entitlement and
must not be repeated. Earlier signing-hold notes are superseded by this direction.

The [November 17 client source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17)
was published once from `a547a4d`. GitHub's archive digest matches the reviewed
archive; anonymous checksum and range reads passed. Publication does not settle
every linked dependency's combined-binary distribution basis.
See [publication](../release/client-source-publication-20261117.json).

The separate [version 3 source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17-v3)
now corresponds to frozen source `87d53cd` and was published once. All 5,905
members were rehashed; 5,892 match the reviewed prior archive, with six additions
and seven changes. GitHub's asset digest matches the reviewed local archive;
anonymous checksum and partial-download checks passed. Earlier releases remain.
See [publication receipt](../release/client-source-publication-v3-20261117.json). The Apple build 2
source supplement is also published as three small additive assets on that same
release, with exact GitHub digests and anonymous downloads verified. It binds
the signed IPA to the public source plus its build-number patch; existing assets
were preserved. See [supplement](../release/apple-build2-source-supplement-20261117/publication-receipt.json).

## Historical access and service checkpoints

The accepted flow is **30 days without payment details**, beginning at original
profile creation, followed by optional **$12/year Base** in the US. Sign-in and
device replacement do not reset it. No automatic charge follows cardless expiry;
saved local history remains readable and exportable.

Both stores' obsolete Base introductory offers were removed once and verified.
Optional **Bot mini $48/year** retains its separate eligible one-month trial and
requires active Base access. Starting Vipi enrolls neither subscription.
See [Google](../qa/subscriptions/cardless-trial-20261117-r01/google-base-offer.json)
and [Apple](../qa/subscriptions/cardless-trial-20261117-r01/apple-base-offer.json).

Before the completed production activations, restricted staging ran the `84c3ff8` baseline plus the narrowly scoped
`privacy-language-20261117-r01` disclosure revision, schema `20261117_01`.
The first privacy activation rolled back after a faulty case-sensitive header
check. A fresh activation with the corrected check completed; public HTTPS
returns the disclosure and `no-store`. Environment, schema, push worker and
timers were preserved. See [rollout](../qa/backend/privacy-language-rollout-20261117-r02/receipt.json). Five owned subjects are now admitted: two complimentary
reviewers, the earlier company tester and two new isolated QA identities.
The new Apple QA profile was created normally with exactly 30 days of access.
Its trial end was subsequently shortened in an explicit synthetic fixture to
test checkout without waiting a month; its original creation and trial-start
timestamps remain unchanged. Only that new user was added to the restricted
sandbox tester set. Other accounts, push configuration and service timers were
preserved. See [admission](../release/owned-qa-identities-20261117-r01/activation-receipt.json)
and [billing fixture](../release/owned-qa-billing-20261117-r01/activation-receipt.json).
The fresh Android peer completed a new PKCE sign-in after the original flow expired,
created its profile and showed Swahili with the 30-day cardless end date. The
backend independently confirmed its original trial dates and one active device.
The two new QA identities were administratively verified; their use does not
qualify self-service signup or email verification delivery. See [peer qualification](../qa/owned-peer-v3-20261117-r01/receipt.json).
The subsequent four-setting r03 production activation completed once:
production mode, enforced subscriptions, no subject allowlist and Apple
Production, preserving reviewer and restricted sandbox sets. The active
environment hash at that checkpoint was
`cee1262cae300c1c4eca3aa24424ac23ae42862fa4a88e52747faee3a1696a83`.
That checkpoint used `privacy-language-20261117-r01`, schema `20261117_01`,
with the legacy Vipi identity authority. The before/after profile and trial
digest was unchanged; readiness returned 200. This activation did not deploy
later shared-identity or deletion migrations and does not prove ordinary
customer signup. See [activation reconciliation](../release/production-settings-20261117-r03/executed-reconciliation.json).
The later shared-login cutover superseded that runtime: the current release is
`shared-identity-e853afa-20261117-r02`, schema `20261117_05`, with environment
hash `26d5927c47bbe5470260c539f43fa3dbffb822d27d921a9c4b3761944ee65609`.
Shared Fallsoft authentication and Vipi-only deletion are active; global
Fallsoft deletion remains disabled. See the [completed cutover](../qa/backend/shared-identity-deployment-20261117-r04/deployment.json).
The WorkOS key was rotated once: the old key returned 401, the new key and API
readiness returned 200, and push, database and timers were preserved. The old
environment and r02 candidate must not be restored. See [rotation](../release/workos-key-replacement-20261117-r01/receipt.json).
Isolated tests cover enforced
expiry, retained trial dates and readable history; they do not prove public
customer behavior. See [deployment](../qa/subscriptions/cardless-trial-20261117-r01/receipt.json).

The TestFlight Base checkout on the fresh Apple QA account displays $12/year
without an introductory offer, and Apple's confirmation explicitly says it is
a test with no charge. Subscribe was confirmed once. The original authorization
completed using the company's saved Chrome credential, without exposing it in
chat or logs. Vipi reports Base active, and independent backend readback found
one verified Apple Sandbox Base entitlement on the exact QA account. A single
same-account, same-device Restore then reported purchases up to date. The same
transaction and expiry remain, with an advanced verification timestamp and no
duplicate entitlement. Temporary credential files were removed and clipboards
cleared. This does not prove clean-device restore, renewal or revocation.
See [purchase](../release/apple-sandbox-purchase-20261117-r01/receipt.json)
and [restore](../release/apple-sandbox-purchase-20261117-r01/restore-receipt.json).

One separate Bot mini Sandbox trial also completed on that account. Apple's
confirmation showed the eligible one-month offer followed by $48/year, with no
charge for the test. Independent readback found its unrevoked Sandbox trial.
One synthetic vBot prompt returned the requested sentence, and usage settled
exactly once: one reply used, 149 remaining, no reserved balance. No human
message or additional prompt was sent. See [Bot trial](../release/apple-sandbox-purchase-20261117-r01/bot-purchase-receipt.json)
and [usage](../release/apple-sandbox-purchase-20261117-r01/bot-usage-receipt.json).

The original no-charge Google license purchase on version 1 activated, renewed,
was canceled and lapsed. No purchase was repeated. Version 2's retained account
shows the dated cardless period. Cross-device purchase restoration remains
unqualified. The original Apple production TEST
returned 401 and was not retried; earlier sandbox evidence is separate.
See [purchase](../qa/subscriptions/google-license-sandbox-20261117-r01/receipt.json),
[lapse](../qa/subscriptions/google-license-sandbox-20261117-r01/lapse.json) and
[Apple TEST](../qa/backend/apple-production-test-20261117-r01/receipt.json).

## Historical messaging and immersion findings

Earlier owned Android foreground messages decrypted and reached Delivered.
Separate FCM checks reached background inbox work and a visible notification;
variable delays do not establish typical latency. The original Android-to-Apple
message reached simulator APNs and decrypted after foregrounding, with Delivered
confirmed. A system banner and production-device APNs delivery remain unproven.
Those original messages must not be resent.

A new company-to-owned-Beta message was submitted **once** on Play version 2
at approximately 06:58 UTC and remains **Waiting to send**. A read-only database
check found its key claim but no current matching envelope. The pending table
is not a historical audit: the subsequent request outcome remains uncertain.
No duplicate send, changed-key acceptance or account reset occurred. Both held Android Vipi packages were subsequently disabled for user 0 while
stopped, preserving their accounts and queued data. Exclusive 5622 was shut
down with its AVD retained; shared 5620 remains running for Pocket and separate
QA. Do not re-enable either held package or reopen the company app until the
original message disposition is resolved. An isolated
R8-minified synthetic harness reproduced a session-establishment exception
before encryption. R8 renamed the JNI callback's `NativeHandleGuard$Owner`
return type; the narrow keep-name rule in `68805f6` fixes that measured failure.
The fixed minified harness passed encryption and peer decryption, with malformed
controls rejected. This does not prove the original message failed for that
reason. Do not update or re-enable the retained app in a way that may retry it.
Private evidence: `investigations/vipi-submit-20261110-r01/android-v2-incoming-20261117-r01/`.

A separate fresh signed-v3 Android peer and owned Apple TestFlight peer exchanged
one message in each direction. Both were delivered and decrypted; Android
automatically showed music as muziki, and Apple showed its Japanese reading.
No prior message was replayed. One Android guest-output recording contains a
low-level nonzero segment, but its speech content and pronunciation remain
unverified. The fresh Android AVD was stopped with account and history preserved.
See [peer receipt](../qa/owned-peer-v3-20261117-r01/receipt.json).

The accepted 007 catalogs support **11 languages and 110 directions**, including
Swahili, with finite coverage. Automatic switching makes no translation-provider
or model-readiness call. Explicit full translation is separate and may need
downloads. Indonesian, Dutch and Russian experiments are not enabled languages.

On actual Play version 2, “I love music.” stayed unchanged under automatic
language detection. Choosing English explicitly produced music/ongaku and
Japanese 音楽 with continuous switching. Listen entered active then idle, but
the emulator had audio disabled. The pinned CLD2 host probe marks that sentence
and two similar English examples unreliable. The new Android classifier and
Apple native fallback now pass the actual local provider route for the same
message into Japanese and Swahili, without model translation calls. The Apple
Simulator visibly shows both ongaku and 音楽 with no language override.
Android's bundled ML Kit uses its default threshold; Apple retains reliable
CLD2 first and considers native fallback at 0.70 only when CLD2 abstains.
Both mask protected text and require two natural words for automatic detection.
These thresholds concern language identification, not translation confidence.
Accepted contextual catalog mappings remain the source of substitutions.
See [Android](../qa/immersion/android-frozen-a52-route-20261117/qualification-receipt.json)
and [Apple](../qa/macos/apple-native-detector-20261117-r01/README.md).

Native catalogs contain 12 UI locales and store copy contains 14 variants.
The [UI review](../qa/ux/review-20261117-r01/REVIEW.md) records Mobbin/Built for Mars
references and bounded fixes for wording, RTL, plans, controls and recovery.
Apple's example controls are reachable above fixed Continue after scrolling.
Accessibility Inspector successfully invoked “Switch music and ongaku” and
updated the visible text and accessibility label. Real VoiceOver traversal,
spoken pronunciation and transient Stop accessibility remain separate checks.

Previously seen words may appear alongside new words within the total display
limit. Zero disables switching. Stable selection and visible dwell record
exposure, not mastery. Familiarity records never authorize a new translation.
Chat backups exclude familiarity-history keys, live messaging keys, unsent
messages and vBot history. One Apple history export was saved and checked before
the company device handoff; it was not restored.

Prior short synthetic playback checks completed across all 110 directions on
both platforms. These prove controller behavior in the recorded environments,
not flawless pronunciation or long-conversation performance. The
[reading audit](../qa/immersion/active-reading-audit-20261116/review.json) checks
required reading structure, not linguistic accuracy. Authored test counts are
not real-conversation coverage percentages. One prior real vBot response settled
its allowance; it is not a typical-latency or quality benchmark.

The installed TestFlight build now has a live English-to-Japanese observation:
the actual vBot reply continuously switches music and ongaku in the same slot,
and the script option displays 音楽. No source-language override was used; Latin
letters were restored afterward. One Listen action entered Stop and returned
to Listen. An app-filtered ScreenCaptureKit recording, with microphone capture
disabled, produced a readable 48 kHz stereo WAV with a non-silent segment and
no clipped samples. Independent ffprobe/ffmpeg analysis confirmed the format
and signal measurements. These observations establish live display and sound
output for that example, not pronunciation accuracy or general conversational
coverage. See [live immersion](../qa/release/apple-signed-build2-20261117-r01/live-vbot-immersion.json)
and [audio evidence](../qa/audio/screencapturekit-20261117-r01/receipt.json).

## Historical open checks and preserved constraints

- Preserve the uncertain original send without replay; resolve its disposition
  before re-enabling either held package or allowing a retry. The separate v3
  owned-peer exchange is qualified, not a resolution of that original outcome.
- At this earlier checkpoint, v4 Android artifact/source and expiry-copy
  qualification were still pending; current v5 evidence supersedes that
  packaging task. Apple Base/Bot purchases and same-device
  restore are qualified, with clean-device recovery and lifecycle limits recorded.
  France and mainland China remain excluded from initial storefronts.
- Reconcile store artifacts, regional export requirements and screenshots.
  France and mainland China are excluded from the initial launch; their
  filing requirements are deferred. The ML Kit/libsignal distribution question is a narrow legal
  interpretation, not an established incompatibility or blanket App Store ban.
  Source publication is complete; the exact bundled SDK terms need focused review.
  See [export assessment](../release/EXPORT_ASSESSMENT.md).
- Google requests an account-wide trader declaration by February 2027. No
  declaration was saved; it is not a current release-preview blocker. It may
  publish company contact details across Fallsoft apps.
- At this earlier checkpoint, public registration and production enforcement
  were not active. The completed shared runtime and fresh Gamma signup above
  supersede that assertion. Store links still wait for independently verified
  public availability.

Canonical source is `/home/ai/Development/vipi-production-20261107`, branch
`delivery/production-20261107`. Apple development uses native macbook-pro; never
restart the retired VM or fleet hosts. The physical iPad remains reserved for other work; iPad Simulator preparation is allowed.
Preserve the nine original experimental modified files, account-bearing emulators,
original signed artifacts and external-action receipts. Auto-reset stays disabled.

Requested cleanup retired approximately 16.10 GB of verified local files across
the recorded passes, plus separately measured Mac cleanup. This is gross removal;
ongoing builds consume space and the number is not net free capacity. Verified
retained artifact routes are in
[artifact retention](../release/artifact-retention-20261117.json). Current source,
release artifacts, accounts and unrelated media were preserved.
