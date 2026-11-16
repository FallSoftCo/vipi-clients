# Android store preparation — updated November 16, 2026

The company Play app now exists as private draft **Vipi**, app ID
`4975664610567218322`. Reviewed listing text, Communication category, support
contact and privacy URL are saved. No build upload, purchase, review submission
or public availability is claimed. The signed `0fda43f` bundle passed local source, configuration, signature, 007
catalog, asset and ARM64 16 KiB alignment checks. Its specified-device
bundletool download estimate is 416,960,679 bytes; four generated splits passed
signer and 16 KiB alignment checks. This is a local estimate, not Play's
calculation or acceptance. The prior `a53ff86` estimate was 416,959,214 bytes.
See `build-artifacts-20261116.json` and `android-store-configuration.json`.
The existing r08 client-source archive predates this build and is not the final
corresponding source. No Play upload or review submission has occurred. Exact-reference
selection and concurrency corrections passed controlled QA; the signed release
APK has not been installed for device testing.

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
subject allowlist. Both accounts now also have explicit complimentary Base and
Bot mini grants, verified in the app. One real Bot request completed in 2.353
seconds and changed the allowance from 150 to 149. That evidence does not
establish Play purchases, unrestricted customer access or background push delivery.

Credentials are in the private reviewer-account store and saved Play App access
fields. Both entries explain language choice, sign-in, **Use this device**, the
other test account and **vBot** from Chats. Reviewers need no payment, trial or
one-time code. Their history stays on their device. Optional Google/partner
feedback testing with those credentials is disabled. The final submitted build
hash still needs to be bound to the review record.

Reviewer procedure: choose the known and learning languages, sign in, open
**Chats**, and open the supplied peer conversation (or use **New chat** and its
exact username). Selected supported words alternate in place; unsupported text
stays unchanged. Chat reading controls include **Pause word switching**, **Original
message**, **Listen**, and, where applicable, **Show original script** / **Show
Latin letters**. **Full translation** is an explicit separate action; missing
models expose **Download for full translation**. Normal word switching requires
no translation-model download. **Your profile and settings** contains **Languages
& downloads**, subscription management and **Delete account**. vBot is optional
and has a separate consent/provider and Bot mini boundary. Its actual provider
reply is qualified for the owned Android account; broader quality and Apple
runtime remain separate. Reviewers must not buy access or start a trial.

The actual retained chat showed English/Swahili mixed speech and Japanese script
and Latin readings. These are finite examples, not a broad vocabulary or voice
quality guarantee. Private candidate catalogs are not shipped merely because
their tests passed; bind screenshots and review notes to the final accepted assets.

## Data Safety preparation

Use `privacy-data-inventory.json` for the data-flow mapping and
`qa/release/play-content-20261111/data-safety.json` for the saved questionnaire.
The final form declares collection, encryption in transit, ten data types and
three shared SDK metric categories. Contacts refers to the readable conversation
graph, not a phone address book. Optional username lookup is processed ephemerally
under the verified live logging configuration. App content shows all ten
declarations actioned; this is not an app-review submission.

| Implemented flow | Declared data and purpose |
|---|---|
| Hosted sign-in/profile | Name, email address, user IDs; account management, functionality and security. |
| Devices, public keys and message routing | Device/other IDs, user IDs, app interactions; functionality and security. Human-chat plaintext remains E2EE; readable routing/delivery metadata does not disappear under that exclusion. |
| Store verification | Purchase history and user IDs; functionality, account binding and fraud prevention. Vipi does not receive card details through this path. |
| Optional vBot and selected reports | Other in-app messages and associated IDs/interactions; functionality, usage limits or abuse handling. These readable submissions are distinct from ordinary E2EE chat. |
| FCM/ML Kit operational data | Device/other IDs, diagnostics and app interactions for the exact SDK/configuration. Disabled Firebase Analytics is not a zero-telemetry claim. |
| Conversation relationships | Contacts/social graph; functionality and security. |
| Exact username lookup | Optional, ephemeral in-app search history; functionality. |

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
calls. The signed `0fda43f` bundle verifies the 007 catalog and included assets;
store admission, final notice reconciliation and provider qualification remain pending.

Do not mark every category optional because vBot/reporting is optional: sign-in
and messaging identifiers are required for their account features. Do not mark
all handling ephemeral, or all transfers “not shared,” from E2EE/TLS alone.
The saved form applies the specific WorkOS/FCM processing exceptions, declares
ML Kit's operational identifiers/interactions/diagnostics shared, and applies
the named user-directed consent exception to optional vBot. These distinctions
remain bound to the configured services. [Google's form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
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

1. Actual Play products/offers and billing/restore/refund/RTDN
   qualification. The new private app requires its first bundle upload before
   subscription products can be configured.
2. Corresponding-source publication and exact dependency distribution basis,
   followed by Play's size/manifest validation of the prepared signed bundle.
3. Final release configuration reconciliation with the saved declarations;
   the live deletion landing page alone does not close the
   outstanding real provider deletion/recovery evidence.
4. Existing FCM configuration and provider delivery, and ordinary Bot mini
   paid-plan qualification. The confirmed Bot response and two foreground human
   messages do not establish background delivery or store transactions.

Private evidence: `android-store-preparation-r01`, `android-live-peer-chat-r01`,
`android-chat-banner-r01` and the two native auth/enrollment receipts in the
November 10 submission investigation. Credentials and subject/key IDs stay there,
not in this repository. Provider/browser ownership remains with the root agent.
