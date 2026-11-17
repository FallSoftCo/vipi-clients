# Current delivery status

Updated November 17, 2026, 08:23 UTC. Vipi remains restricted staging. Neither
app has been submitted for public review. Prior revisions and the linked
receipts retain historical actions; do not replay them.

## Artifacts and stores

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
No version 3 upload, publication or retained-account update has occurred.
See [candidate](../qa/immersion/android-v3-candidate-20261117/candidate.json).

Google's 14 localized listings were field-checked and saved once. Independent
reload verified the locale inventory and English, Swahili and Arabic field
samples. They are ready to send for review, not approved. The production draft
still uses version 1, with countries unselected; reconcile it with the eventual
qualified release before submission. Existing artwork declarations and actual
app screenshots remain. See [localization](../release/google-localized-listing-20261117.json).

Apple's original signed **1.0 (1)**, source `4908d4e`, was delivered once and
finished processing. It remains **Missing Compliance**. Current localized source
`7dd2929` has a qualified full unsigned build with dependency/privacy resources.
The subsequent native detector candidate `a3c77ae` has passed an isolated full
Simulator build and visible automatic Japanese switching; it is not signed.
Eight actual Simulator screenshot candidates use production views and synthetic
messages; these are not live-account or uploaded-store evidence. Privacy,
reviewer access and manual release are saved. Reviewed text is now saved and
reload-verified in all 13 Apple-supported locales. Swahili is not an ASC locale;
new locales retain inherited English keywords and URLs. Required screenshots,
build association and purchase qualification remain incomplete. The application
supports iPad; required iPad Simulator screenshots are being prepared without
using the reserved physical device.
See [Apple configuration](../release/apple-store-configuration.json).

**The owner's Mac signing/keychain hold remains. Do not retry signing or upload
until that dependency changes.** Historical successful signing does not remove
this later hold.

The [November 17 client source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-17)
was published once from `a547a4d`. GitHub's archive digest matches the reviewed
archive; anonymous checksum and range reads passed. Publication does not settle
every linked dependency's combined-binary distribution basis.
See [publication](../release/client-source-publication-20261117.json).

A separate private archive now corresponds to frozen version 3 source `87d53cd`.
All 5,905 members were rehashed; 5,892 are unchanged from the reviewed prior
archive, with six additions and seven changes for the native fixes and notices.
It is not yet published. See [candidate source](../release/client-source-candidate-v3-20261117.json).

## Access and service

The accepted flow is **30 days without payment details**, beginning at original
profile creation, followed by optional **$12/year Base** in the US. Sign-in and
device replacement do not reset it. No automatic charge follows cardless expiry;
saved local history remains readable and exportable.

Both stores' obsolete Base introductory offers were removed once and verified.
Optional **Bot mini $48/year** retains its separate eligible one-month trial and
requires active Base access. Starting Vipi enrolls neither subscription.
See [Google](../qa/subscriptions/cardless-trial-20261117-r01/google-base-offer.json)
and [Apple](../qa/subscriptions/cardless-trial-20261117-r01/apple-base-offer.json).

Restricted staging runs backend `84c3ff8`, schema `20261117_01`, activated once
and independently checked. Three owned subjects are admitted: two complimentary
reviewers and a separate company tester. Public registration is closed and
subscription enforcement is disabled on staging. Isolated tests cover enforced
expiry, retained trial dates and readable history; they do not prove public
customer behavior. See [deployment](../qa/subscriptions/cardless-trial-20261117-r01/receipt.json).

The original no-charge Google license purchase on version 1 activated, renewed,
was canceled and lapsed. No purchase was repeated. Version 2's retained account
shows the dated cardless period. Cross-device purchase restoration and an actual
Apple sandbox purchase remain unqualified. The original Apple production TEST
returned 401 and was not retried; earlier sandbox evidence is separate.
See [purchase](../qa/subscriptions/google-license-sandbox-20261117-r01/receipt.json),
[lapse](../qa/subscriptions/google-license-sandbox-20261117-r01/lapse.json) and
[Apple TEST](../qa/backend/apple-production-test-20261117-r01/receipt.json).

## Current messaging and immersion findings

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
No duplicate send, changed-key acceptance or account reset occurred. An isolated
R8-minified synthetic harness reproduced a session-establishment exception
before encryption. R8 renamed the JNI callback's `NativeHandleGuard$Owner`
return type; the narrow keep-name rule in `68805f6` fixes that measured failure.
The fixed minified harness passed encryption and peer decryption, with malformed
controls rejected. This does not prove the original message failed for that
reason. Do not update its retained app or publish an update that may retry it.
Private evidence: `investigations/vipi-submit-20261110-r01/android-v2-incoming-20261117-r01/`.

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

## Remaining work and constraints

- Finish exact version 3 runtime checks for the qualified session and short-message
  routing fixes. Preserve the uncertain original send without replay; resolve its
  disposition before any retained-account update or automatic retry.
- Deploy the matching detected-language privacy detail before the new Android
  candidate becomes publicly available. An immutable candidate with only the
  public-page production change is staged and standalone-tested; it is not active.
  Activation must reconcile live API connections and the original message hold.
- Complete current Apple qualification when its signing dependency changes,
  actual purchase/restore and production notification evidence.
- Reconcile store artifacts, regional export requirements and screenshots.
  France needs a current company extract; China-specific requirements and the
  exact linked ML Kit/libsignal distribution basis remain unresolved.
  See [export assessment](../release/EXPORT_ASSESSMENT.md).
- Google requests an account-wide trader declaration by February 2027. Its
  existing profile was reviewed; no declaration was saved. Approval was requested
  because it publishes company contact details for all Fallsoft apps.
- Enable customer registration/enforcement only after a qualified first-use,
  friend-chat and paid-access flow. Public pages currently identify Vipi as testing.

Canonical source is `/home/ai/Development/vipi-production-20261107`, branch
`delivery/production-20261107`. Apple development uses native macbook-pro; never
restart the retired VM or fleet hosts. The iPad remains reserved for other work.
Preserve the nine original experimental modified files, account-bearing emulators,
original signed artifacts and external-action receipts. Auto-reset stays disabled.

Requested cleanup retired approximately 16.10 GB of verified local files across
the recorded passes, plus separately measured Mac cleanup. This is gross removal;
ongoing builds consume space and the number is not net free capacity. Verified
retained artifact routes are in
[artifact retention](../release/artifact-retention-20261117.json). Current source,
release artifacts, accounts and unrelated media were preserved.
