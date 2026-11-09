# Store submission preparation

These are reviewable drafts. Private Apple app `6832624092`, **Mambo Vipi:
Language Chat**, has been created under the company account with bundle
`co.fallsoft.vipi`. No release binary or review submission has been uploaded.
`docs/DELIVERY_STATUS.md` records current acceptance and blockers.
The company is **Fallible Software, Co.**, using its FallSoft.Co accounts.
Do not use the unrelated personal developer account or qualification build 63.

`privacy-data-inventory.json` maps implemented data flows and pinned SDK
declarations to candidate store categories. It records remaining questions and
source hashes; it is not a completed questionnaire. Reconcile it with the final
signed binaries, provider configuration and deployed notice before submission.

## Listing and screenshots

`store-metadata-en-US.json` contains the proposed English copy, working policy
URLs and separate-plan disclosure. Populate console fields from the appropriate
values, not the entire JSON. Confirm names and categories in the actual console.
The marketing URL currently uses the existing HTTPS API origin; configuring the
apex domain remains separate work. No nonexistent store-download links belong
on the public homepage.

Capture the final submitted app, with synthetic review conversations and no
account email, credentials or private customer content. Use actual UI and
complete inspectable screenshots for these views:

1. A readable chat with an in-place immersion phrase and its familiar meaning.
2. The same message's complete translation, with ordinary Latin-letter reading
   for a non-Roman language and the real Listen control.
3. The concise immersion-language selection and interactive onboarding preview.
4. The real friend invitation/conversation flow.
5. vBot only after the real provider and optional plan work end to end.

Keep text large enough to read in a store preview. Caption the benefit of the
visible interaction; do not add controls or results absent from the app. Light,
dark, large-text and RTL/device-size QA are validation work, not a requirement
to crowd every listing image with multiple variants. Final sizes and required
device families come from the current store console.

The current [Google Play limits](https://support.google.com/googleplay/android-developer/answer/9859372?hl=en) allow a 500 MB compressed base module; the older 200 MB assumption is not the current base limit. The retained ARM64 qualification estimates about 407 MB, but that blank-auth/debug-signed qualification must never be uploaded. Re-measure the final signed build and confirm the console calculation. See `store-size-constraints.json`.

## Reviewer access

Use an owned review account against the real release environment, with a
separate consenting test peer and synthetic message history. Record credentials
only in the private review-access store and actual console review fields.
Provide both base and Bot mini access needed to inspect advertised features.
Do not point reviewers at the example.net staging accounts, a one-time-code
flow that cannot complete, or a disabled provider.

Review notes should explain the observable behavior:

- Choose the language already known and the immersion language, then complete
  the explicit store subscription flow. The optional Bot mini subscription is
  offered when entering vBot; it is not required during base onboarding.
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

## Evidence required before upload/submission

| Item | Required evidence |
|---|---|
| Company access | Correct organization selected; current agreements accepted by the appropriate account holder; app identifiers and signing profile verified. |
| Subscription products | Actual annual base and Bot mini products, independent eligible one-month trials, localized prices, separate Apple subscription groups, usable restore/manage flows. |
| Store authority | Real sandbox purchase, renewal, refund/revocation and restore; authenticated Apple test notification and Google RTDN receipt; account binding and lapse behavior. |
| Background delivery | Real APNs/FCM registration and delivery on physical devices, denied-permission recovery, reconnect and expiry. |
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

Current policy references, checked November 8, 2026:
[Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/),
[Google User Data](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en),
[Google listing metadata](https://support.google.com/googleplay/android-developer/answer/9898842?hl=en).
These support accurate listings, working reviewer access and disclosed data
handling; they are not an approval guarantee. The draft remains gated on the
actual submitted product and current console requirements.
