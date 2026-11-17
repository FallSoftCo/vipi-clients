# Current delivery status

Updated November 17, 2026. Vipi remains restricted staging. Neither
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

Restricted staging runs the `84c3ff8` baseline plus the narrowly scoped
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
The new Android peer remains at a human-verification challenge, with no profile
or message created. The new QA identities were administratively verified;
their use does not qualify email verification delivery.
Public registration is closed and
subscription enforcement is disabled on staging. A proposed production configuration
passed the deployed settings validators in memory: production mode, enforced
access, no subject allowlist and Apple Production, preserving the scoped reviewer
and sandbox tester sets. That historical proposal was not activated and must
be rebased on the current environment, whose SHA-256 is
`4082efd72eca75e310b7cf57c873338b757796e7761a8a7c318432b97f3cba64`.
This establishes
configuration validity and credential-file readability, not public signup or
provider authorization. See [candidate receipt](../qa/release/production-settings-candidate-20261117-r01/validation-receipt.json).
Isolated tests cover enforced
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
No duplicate send, changed-key acceptance or account reset occurred. Both owned
Android Vipi app processes were force-stopped at 09:20 UTC, preserving accounts
and queued data; the emulators and other applications remain running. Do not
reopen the company app until the original message disposition is resolved. An isolated
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
- Complete isolated Apple purchase/restore and first-use/friend-chat
  qualification. Signing, delivery, encryption declaration and build association
  are complete. The owner excluded France and mainland China; the saved app and
  subscription settings reflect that choice. No government filing is being made.
- Reconcile store artifacts, regional export requirements and screenshots.
  France and mainland China are excluded from the initial launch; their
  filing requirements are deferred. The ML Kit/libsignal distribution question is a narrow legal
  interpretation, not an established incompatibility or blanket App Store ban.
  Source publication is complete; the exact bundled SDK terms need focused review.
  See [export assessment](../release/EXPORT_ASSESSMENT.md).
- Google requests an account-wide trader declaration by February 2027. Its
  existing profile was reviewed; no declaration was saved. Approval was requested
  because it publishes company contact details for all Fallsoft apps.
- Enable customer registration/enforcement only after a qualified first-use,
  friend-chat and paid-access flow. Public pages currently identify Vipi as testing.

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
