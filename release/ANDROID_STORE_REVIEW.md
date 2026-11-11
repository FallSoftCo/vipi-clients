# Android store preparation — November 11, 2026

The company Play app now exists as private draft **Vipi**, app ID
`4975664610567218322`. Reviewed listing text, Communication category, support
contact and privacy URL are saved. No build upload, purchase, review submission
or public availability is claimed. The signed `6ceaf4b` bundle passed local
source, configuration, signature, catalog, notice and ARM64 16 KiB checks;
its specified-device download estimate is 416,946,355 bytes. Play has not accepted
or measured it. See `build-artifacts-20261111.json` and
`android-store-configuration.json` for the current evidence.

## Product and reviewer access

The app is **Vipi**. Its base subscription is displayed as **Vipi**; **Bot mini**
is a separate optional subscription requiring active Vipi access. Android product
IDs in `Subscriptions.kt` are `vipi_base` and `vipi_bot_mini`. Do not copy the
Apple product IDs into Play. The intended US annual prices ($12 and additional
$48) and separate eligible one-month trials remain listing drafts until the
actual Google offers are configured and read back. The app displays store offers,
not a locally invented price or eligibility result.

Owned Alpha and Beta accounts completed real production-WorkOS PKCE, profile
creation, device enrollment and a two-message native encrypted exchange on the
restricted staging service. Both messages were decrypted and marked Delivered.
This service still has subscription enforcement disabled and an explicit review
subject allowlist. That evidence does not establish Play purchase, reviewer
entitlement, unrestricted customer access or background push delivery.

Keep credentials in the private reviewer-account store and eventual Play App
access fields only. Fill these placeholders after the final reviewer environment
and access have been verified:

- Reviewer login: `<PRIVATE_REVIEW_ALPHA_CREDENTIAL_REFERENCE>`.
- Peer login/username: `<PRIVATE_REVIEW_BETA_CREDENTIAL_REFERENCE>` /
  `<VERIFIED_REVIEW_PEER_USERNAME>`.
- Submitted version/build: `<FINAL_PLAY_VERSION_AND_BUNDLE_HASH>`.
- Base/Bot mini access: `<VERIFIED_REVIEW_ENTITLEMENT_AND_OFFER_RECEIPT>`.

Reviewer procedure: choose the known and learning languages, sign in, open
**Chats**, and open the supplied peer conversation (or use **New chat** and its
exact username). Selected supported words alternate in place; unsupported text
stays unchanged. Chat reading controls include **Pause word switching**, **Original
message**, **Listen**, and, where applicable, **Show original script** / **Show
Latin letters**. **Full translation** is an explicit separate action; missing
models expose **Download for full translation**. Normal word switching requires
no translation-model download. **Your profile and settings** contains **Languages
& downloads**, subscription management and **Delete account**. vBot is optional
and has a separate consent/provider and Bot mini boundary; do not advertise it
as qualified until real provider/plan access works. Do not ask reviewers to buy
access merely to compensate for missing reviewer provisioning.

The actual retained chat showed English/Swahili mixed speech and Japanese script
and Latin readings. These are finite examples, not a broad vocabulary or voice
quality guarantee. Private candidate catalogs are not shipped merely because
their tests passed; bind screenshots and review notes to the final accepted assets.

## Data Safety preparation

Use `privacy-data-inventory.json` for the full data-flow mapping. The draft answer
to whether this account-based app collects data is **yes**. The following are
candidate categories to reconcile in the final Play form, not an already-submitted
set of answers:

| Implemented flow | Candidate data and purpose |
|---|---|
| Hosted sign-in/profile | Name, email address, user IDs; account management, functionality and security. |
| Devices, public keys and message routing | Device/other IDs, user IDs, app interactions; functionality and security. Human-chat plaintext remains E2EE; readable routing/delivery metadata does not disappear under that exclusion. |
| Store verification | Purchase history and user IDs; functionality, account binding and fraud prevention. Vipi does not receive card details through this path. |
| Optional vBot and selected reports | In-app messages/other user content and associated IDs/interactions; functionality, usage limits or abuse handling. These readable submissions are distinct from ordinary E2EE chat. |
| FCM/ML Kit operational data | Device/other IDs, diagnostics, app interactions/performance data as applicable to the exact SDK/configuration. Disabled Firebase Analytics is not a zero-telemetry claim. |

Automatic CLD2 identification, approved word/phrase lookup, readings and local
speech do not send message text to a translation service. Automatic misses retain
the original. Google translation remains linked. The unused direct Android ML Kit language-ID
dependency and its now-unresolved language-ID-common artifact were removed;
the identification adapter uses CLD2. Optional explicit full translation, model-download
traffic and retained SDK operational disclosures must still be accounted for.
Current pinned Android dependencies include ML Kit translate 17.0.3, Firebase
Messaging 26.0.1, WorkOS 0.4.0 and Billing 9.1.0. The generated Android notices
were refreshed from the offline resolved releaseRuntimeClasspath after the
language-ID removal. The combined canonical -007 debug build confirms the
language-ID classes are absent, translate classes and CLD2 remain, and all32
focused native routes preserve originals with zero automatic translation/readiness
calls. The current signed `6ceaf4b` bundle also verifies the final catalog and
notices; store admission and provider qualification remain pending.

Do not mark every category optional because vBot/reporting is optional: sign-in
and messaging identifiers are required for their account features. Do not mark
all handling ephemeral, or all transfers “not shared,” from E2EE/TLS alone.
Service-provider and user-directed-sharing exceptions require the actual contract
and flow. The remaining classification work is the existing SDK/provider
configuration and vBot processing-terms reconciliation, not a new local-detector
privacy dependency. [Google's form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
and [ML Kit's Android disclosure](https://developers.google.com/ml-kit/android-data-disclosure)
were read on November 11; the latter describes latest SDKs, so pinned-version
reconciliation remains explicit.

## Permissions and deletion

The app source declares INTERNET, ACCESS_NETWORK_STATE and POST_NOTIFICATIONS.
The retained release merged manifest additionally declares WAKE_LOCK,
`com.google.android.c2dm.permission.RECEIVE`, RECEIVE_BOOT_COMPLETED,
FOREGROUND_SERVICE, `com.android.vending.BILLING`, and the package's signature-only
DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION. These support networking, scheduled
background delivery, billing and protected internal receivers. No contacts,
microphone, location, camera, broad storage or advertising-ID permission appears
in that inspected manifest. It is historical merged evidence; inspect the final
bundle's merged manifest again after the final source/configuration is built.
Listen uses local synthesis and does not require microphone access. History
export/import uses the user-selected document route, not broad storage access.

The listing deletion URL is **https://api.mambovipi.app/delete-account**.
Unauthenticated GET returned HTTP 200 on November 11 with **Sign in to continue**,
a separate review/confirmation step, and subscription/copy limitations. Privacy,
terms and help also returned HTTP 200. No sign-in or deletion was performed in
this pass. URL availability is not a fresh end-to-end provider-deletion receipt.

In-app **Delete account** opens an explicit confirmation. The native deletion
journal can request **Sign in to confirm** for the same account and show
**Deletion requested** / **Check status** until completion. Native completion
also erases this device's saved chats. Browser deletion cannot remotely erase
other devices' local histories. Friends' copies and user-exported backups remain;
store subscriptions are managed separately, and cancellation is not a prerequisite
for requesting deletion. Server sign-in deletion retries and limited retained
receipts/backups must follow the published notice; do not promise instant erasure
of every copy. Google requires both in-app and web deletion routes for apps with
account creation; see its [deletion guidance](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en).

## Remaining external gates

1. Actual Play products/offers, reviewer access and billing/restore/refund/RTDN
   qualification. The new private app requires its first bundle upload before
   subscription products can be configured.
2. Corresponding-source publication and exact dependency distribution basis,
   followed by Play's size/manifest validation of the prepared signed bundle.
3. Final Data Safety/App access/deletion form entries and release configuration
   reconciliation; the live deletion landing page alone does not close the
   outstanding real provider deletion/recovery evidence.
4. Existing FCM configuration/provider-delivery and vBot provider/terms/plan gates
   for any features included in the submitted listing. The two foreground native
   messages do not close either gate.

Private evidence: `android-store-preparation-r01`, `android-live-peer-chat-r01`,
`android-chat-banner-r01` and the two native auth/enrollment receipts in the
November 10 submission investigation. Credentials and subject/key IDs stay there,
not in this repository. Provider/browser ownership remains with the root agent.
