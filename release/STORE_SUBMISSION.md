# Store submission handoff

The [free-launch candidate](store-metadata-en-US.json) and [review notes](free-launch-review-en-US.md) supersede the submission copy below. The dated records document earlier releases.

## Current release boundary — November 17 / November 18 UTC

Google production **1.0.4 (5)** was sent for review once at **00:29:54 UTC**
on November 18. The console reported **24 changes sent for review**, and
**Changes in review** persisted after reload. At 00:37 UTC, preliminary checks had passed and the
console stated that the changes are now in review. Approval and public rollout
are not established. Do not send it again.
See [terminal Google receipt](google-play-review-submission-20261117.json).

The submitted AAB is SHA-256
`108e1152a8bf50d93e2d4ab9fd4d464aaf5ca04a9a36a25fc3f6bd0c6383714d`,
from frozen source **55a9f723f436f4252730c0a85358a9aa32080f8b**.
The matching production APK, all four ABIs, source/assets, signatures and
16 KiB alignment were qualified. See [artifacts](android-v5-artifacts-20261117.md).
Google's 14 localized listings now describe the actual single-tap controls;
four current actual UI frames and exact read-back Gamma credentials were saved
before submission. No credentials belong in repository documentation.

Apple **1.0 (4)** was signed/qualified and delivered once at approximately
**00:24 UTC** on November 18. Its **431,015,828-byte** IPA has SHA-256
`ac1851a2d5947c86552204b1c32ce1f16801dc351d1275b53590ba189b5da416`.
Processing and export compliance are complete. The app, both annual subscriptions
and both subscription groups were **submitted once at 02:22:45 UTC** on November 18.
The five items show **Waiting for Review**, verified again after reload at 02:24 UTC.
Submission ID is `f4a7f2c9-4d69-43be-9c4b-35a7abf6d0cc`; manual release remains set.
All 13 descriptions, localized keywords, support/privacy URLs, six current public
screenshots and exact Alpha review access were saved before submission. Private
subscription reference captures disclose their historical build 2 provenance
and typography limits. See [terminal Apple receipt](apple-review-submission-20261117.json).
Neither approval nor public availability is established. The private `ios-release-packaging-r01`
qualification/export receipts retain the pre-upload checks; their zero-upload
fields are historical and do not negate the later delivery. Do not repeat it.

The exact native-redesign source supplement was published and anonymously
verified on the existing public source release. See [terminal source receipt](native-redesign-source-publication-20261117.json).
The earlier [v5 draft receipt](android-v5-store-upload-20261117.json) and its
remaining-work list precede the completed reviewer, screenshots, source and
submission proofs and must not be used as the current gate list.

## Current service and reviewer flow

Shared Fallsoft authentication, schema 05, Vipi-only deletion and subscription
enforcement are live. Exact verified owner/Gamma testing grants are active;
they do not fabricate purchases or bypass deleted/suspended accounts.
See [deployment](../qa/backend/shared-identity-deployment-20261117-r04/deployment.json)
and [grant activation](../qa/backend/owned-testing-access-20261117-r01/deployment.json).
Global Fallsoft deletion remains disabled until all affected applications are covered.

Fresh Gamma shared sign-in and normal username setup passed on the exact
Android v5 release. The app showed review access and a ready device. One
consented vBot prompt produced an actual reply, with **149/150** remaining and
one independently verified settled debit, no pending requests and no purchases.
Chinese tone-marked readings, one-tap speech and same-tap Stop were observed.
The fourth frame shows preserved, already-delivered synthetic friend history;
no new friend message was sent. See [native review](../qa/ux/android-release-live-20261117-r01/REVIEW.md)
and [independent accounting](android-v5-owned-review-live-access-20261117.json).

Current Android review instructions use the saved Gamma credentials through
**Continue with Fallsoft**, after choosing the known and learning languages.
Review access requires no purchase or trial. Whole sent and received messages
are translated automatically into the practice language. Available non-Latin
reading guides appear in Latin letters by default; Chinese pinyin includes tone
marks. Tap a message to hear its full practice-language text; tap the playing
message to stop. Hold the message area to reveal all meanings in the known
language; release to restore the prior script view. Double-tap a message to
switch the script view for all visible messages between reading guides/native
script. Hold and double-tap are silent. The header
speaker enables autoplay only for new sent/received messages, without replaying
history; turning it off stops and clears pending audio. Copy original remains a
native header-menu action. Downloaded local models, guide and voice availability
are reported truthfully; translation and reading mistakes remain possible.
vBot is optional, requires its separate consent, and has a disclosed provider boundary.
Friend chats are end-to-end encrypted; vBot and selected reports have separate
readable-service boundaries.

Ordinary Base access starts with 30 days without a card from original profile
creation; afterward the user chooses whether to subscribe. No automatic charge
follows that cardless period. The optional Bot mini plan retains its separate
eligible one-month store trial and requires Base. Actual localized store prices
are shown before purchase; reviewer grants are not billing qualification.

## Current remaining handoff

Observe both stores' review outcomes without resending either submission. Google
preliminary checks passed; Apple is Waiting for Review. The user's phone still
reported versionCode **4** at **01:55 UTC**;
the verified v5 APK transfer and one installer opening do not prove installation.
Preserve original company/Beta held data and the unresolved old send. Earlier
billing, restore, push and translation observations retain their exact limits;
this handoff does not claim universal linguistic accuracy or complete lifecycle
coverage. See [current delivery status](../docs/DELIVERY_STATUS.md).

## Historical narrative — not current submission instructions

The following earlier snapshots retain completed actions, prior artifacts,
checklists and original uncertainty. Claims of “no review,” older builds being
“current,” two screenshots or older reviewer credentials apply only to their
recorded checkpoint. The current sections and terminal receipts above supersede
those statements. Do not replay their uploads, purchases, authentication or sends.

## Historical store preparation

The app is **Vipi**, with **Vipi: Immersive Chat** as the saved listing
name on both stores and **Immersive chat with friends.** as the opening headline. Private Apple
app `6832624092` belongs to the company account, bundle `co.fallsoft.vipi`.
The current company-signed 1.0(2) IPA was delivered once through Transporter
on November 17; Transporter reports processing finished. Its production push entitlement, disabled
debugging and exact IPA signature/hash were verified. The original 1.0(1)
delivery remains preserved. No app-review submission has occurred. Both
Google's 14 and Apple's 13 supported reviewed localized listings are saved and
reload-verified. The earlier assumption that new Apple locales inherited English keywords and URLs was incorrect: final validation found missing fields. All 13 locales now have explicitly saved and verified localized keywords, support URLs and privacy URLs; see `localizations/apple-final-fields-20261117.json`.
Build 2 includes the current Apple fixes; see `apple-delivery-build2-20261117-r01.json`.
`docs/DELIVERY_STATUS.md` records current acceptance and blockers.
The company is **Fallible Software, Co.**, using its FallSoft.Co accounts.
Do not use the unrelated personal developer account or qualification build 63.

Google Play private app `4975664610567218322` now exists as **Vipi: Immersive Chat** in company
account `4750854689150545006`, package `co.fallsoft.vipi`. Its reviewed text,
Communication category, support contact, privacy URL, icon, feature graphic and
two actual Android chat screenshots are saved. All ten app-content declarations
are complete, including two reviewer accounts, the 13+ target audience and Data
Safety. The console shows none needing attention. Creation
preceded content setup and publication in the documented Play workflow. The
original signed Android bundle was uploaded once; subsequent internal release
`2` is now installed through Play by the single owned company tester. Version 3
has completed signed-artifact and isolated offline UI checks, uploaded once to
the artifact library, and replaced version 1 in the existing production draft.
All 14 release-note translations were saved and reloaded exactly. No version 3
track publication, retained-account update or public review has occurred. The corrected `EXPORT_ASSESSMENT.md` remains
its technical export basis. Exact linked-binary distribution terms remain a
separate release consideration. Both annual subscriptions are active. Base has
30 cardless days from original profile creation and no store introductory offer;
Bot mini retains its separate eligible one-month store trial. Company Google browser/CLI authentication is
restored. The existing push worker now has a dedicated FCM sender configured;
one real background delivery completed after several minutes. A distinct
diagnostic message has direct FCM HTTP 200, background inbox and visible
notification evidence. Its five-minute delivery delay remains under investigation.
Store products and registration alone do not qualify transactions or delivery.

`privacy-data-inventory.json` maps implemented data flows and pinned SDK
declarations. Its November 16 incremental review covers local familiarity
records and their chat-backup exclusion; the earlier Google questionnaire
readback remains dated and was not resubmitted. Apple's privacy questionnaire
was published and manual release mode saved, as recorded in
`apple-privacy-20261117-r01.json`. Final signed binary/configuration reconciliation
remains separate work.

## Historical listing and screenshot procedure

`localizations/reviewed-platform-fields.json` contains the reviewed platform
copy, working policy URLs and separate-plan disclosure. Populate console fields from the appropriate
values, not the entire JSON. Confirm names and categories in the actual console.
The marketing URL currently uses the existing HTTPS API origin; configuring the
apex domain remains separate work. No nonexistent store-download links belong
on the public homepage.

Capture the final submitted app, with synthetic review conversations and no
account email, credentials or private customer content. Use actual UI and
complete inspectable screenshots for these views:

1. A readable chat with an in-place immersion phrase and its familiar meaning.
2. The same automatic word/phrase result in original script and Latin letters,
   with the real Listen control. Add a full-translation screenshot only after
   that separate optional action is qualified in the submitted build.
3. The concise immersion-language selection and interactive onboarding preview.
4. The real friend invitation/conversation flow.
5. vBot only after the real provider and optional plan work end to end.

Keep text large enough to read in a store preview. Caption the benefit of the
visible interaction; do not add controls or results absent from the app. Light,
dark, large-text and RTL/device-size QA are validation work, not a requirement
to crowd every listing image with multiple variants. Final sizes and required
device families come from the current store console.

The checked [Google Play limits](https://support.google.com/googleplay/android-developer/answer/9859372?hl=en) allow a 500 MB compressed base module; the older 200 MB assumption is not the current base limit. The signed `0fda43f` bundle estimated 416,960,679 bytes for the retained ARM64, English, 420 dpi, SDK 35 device configuration. Its four generated splits passed upload-signer and 16 KiB alignment checks. Google subsequently accepted versions 1 and 2 and displayed a 417 MB new-install download. Version 3 passed its own package and alignment checks and Play shows 418 MB for a new install. Earlier blank-auth/debug-signed qualification artifacts must never be uploaded. The November 17 public source preview is pinned to `a547a4d`; its hash and anonymous download were verified. It predates the new classifier and JNI keep-name fix and is not corresponding-source evidence for version 3. The separate `source-preview-2026-11-17-v3` publication now matches version 3; prior publications were preserved. Source publication does not settle the separate linked-dependency distribution question. See `client-source-publication-v3-20261117.json`, `client-source-publication-20261117.json`, `android-build-artifacts-20261117.json` and `store-size-constraints.json`.

## Historical reviewer-access procedure

Android-specific current labels, Data Safety candidates, merged permissions,
deletion readback and exact access limits are in `ANDROID_STORE_REVIEW.md`.
The verified two-account native exchange used restricted staging with production
WorkOS and subscription enforcement disabled. Explicit complimentary Base and
Bot mini grants were subsequently verified, including one actual Bot response.
Play App access now contains both accounts and device-replacement instructions.
This is reviewer access evidence, not Play billing qualification.

Use an owned review account against the real release environment, with a
separate consenting test peer and synthetic message history. Record credentials
only in the private review-access store and actual console review fields.
Provide both base and Bot mini access needed to inspect advertised features.
Do not point reviewers at the example.net staging accounts, a one-time-code
flow that cannot complete, or a disabled provider.

Review notes should explain the observable behavior:

- Choose the language already known and the language to learn, then sign in
  using the supplied review account. Verified review accounts receive
  complimentary access and must not purchase or start a trial. Check that the
  app shows “Review access is active.” Ordinary customers receive
  30-day cardless access before an optional annual Base purchase; Bot mini remains
  a separate optional plan.
- Use the supplied test peer/invitation to inspect human messaging. Vocabulary
  alternates in the same bubble while idle. Composing, scrolling and listening
  pause the changes. Full translation is a separate message action.
- Human messages are end-to-end encrypted. vBot has a separate disclosed
  provider boundary. A report shares only the selected content after consent.
- Settings exposes account deletion, subscription management, history export,
  language storage and license notices. Lapsed subscriptions preserve access
  to existing local history/export and account deletion.

Replace this procedural draft with exact verified screen/control labels and
the final build/provider configuration before sending it to a reviewer.

## Historical evidence checklist

| Item | Required evidence |
|---|---|
| Company access | Correct organization selected; current agreements accepted by the appropriate account holder; app identifiers and signing profile verified. |
| Subscription products | Actual annual Base and Bot mini products, 30 cardless days for Base, a separate eligible one-month Bot mini store trial, localized prices, separate Apple subscription groups, usable restore/manage flows. |
| Store authority | Real sandbox purchase, renewal, refund/revocation and restore; authenticated Apple test notification and Google RTDN receipt; account binding and lapse behavior. |
| Background delivery | Real APNs/FCM registration and delivery in supported native simulator/emulator environments, denied-permission recovery, reconnect and expiry. Retain the exact environment and delivery evidence; direct callback tests or locally injected notifications do not prove provider delivery. The owner has reserved the iPad for 8bar Club. |
| vBot | Actual provider response and cancellation, visible reply allowance, spending controls, consent and selected-report behavior. |
| Privacy | Final SDK/network inventory reconciled with actual store privacy/data-safety forms, app manifests and deployed policy text. E2EE does not justify claiming zero service metadata. |
| Safety operations | Working block/report/delete paths and a real owner for timely review through the published company contact. A CLI alone does not establish operational response. |
| Build/source | Final signed release hash/version, device/ABI qualification, dependency notices and complete corresponding-source publication for the shipped clients. |
| Experience | Accepted conversational coverage/progression and native readings/audio; polished onboarding, themes, navigation, accessibility and actual screenshots. |
| Recovery | Proven backup restore with post-snapshot deletions/restrictions, billing/spend reconciliation and explicit device re-enrollment before reopening. |

Do not fabricate age-rating, encryption/export-compliance or privacy answers.
Complete the current questionnaires from the exact released behavior and
dependencies. Save each app/product/build/submission ID and receipt before a
subsequent external action, and inspect an uncertain result before retrying it.

Current signing authorization: the owner explicitly directed “you must sign” on
November 17. The proven signed Xcode archive and automatic Organizer export
route completed for build 2; the final IPA passed verification and its single
Transporter upload was delivered and finished processing. Fresh ASC readback
confirmed the processed build, and the subsequent standard-encryption/FranceNo
declaration is saved. Build 2 is associated, the app download is Free, and app
and both subscriptions exclude France/mainland China (173 storefronts). Google
production draft excludes the same countries (176 grouped entries); its preview
is Ready to release. These changes do not submit review or qualify purchases.
Earlier signing-hold notes are superseded. The original company Android account
separately retains an uncertain queued message. Do not resend, reset
the account, accept a changed peer key or publish/install an update that may
resume it before its disposition is resolved. Isolated synthetic qualification
uses separate packages and does not settle that original external outcome.

Current policy references, checked November 8, 2026:
[Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/),
[Google User Data](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en),
[Google listing metadata](https://support.google.com/googleplay/android-developer/answer/9898842?hl=en).
These support accurate listings, working reviewer access and disclosed data
handling; they are not an approval guarantee. The draft remains gated on the
actual submitted product and current console requirements.
