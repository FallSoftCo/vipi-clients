# Current delivery status

Updated 2026-11-16. Vipi remains restricted staging, not a submitted or publicly
available store release. This page describes current operational state;
[VERIFICATION.md](VERIFICATION.md) and the linked receipts retain historical
experiments, failures and qualification limits. The longer prior status remains
in Git history before this revision.

## November 16 update

The new progression retains previously displayed words alongside new words.
The **New words** setting controls the allowance for unfamiliar words; familiar
words can appear in addition, within the existing total limit. Zero turns word
switching off. A complete visible target-language dwell records an exposure,
not a claim that the word has been learned. Selection stays fixed while the
message is visible or in flight, so its own exposure does not keep changing it.

Both platforms implement account-local encrypted history for reviewed frames
and guarded English→Japanese/Swahili starter entries. Learning identities survive
unrelated catalog expansions and retain meaning, reading and entry boundaries.
History never approves a translation or weakens a source guard. Current chat
backups do not include this familiarity history or its account-local identifier
key. Do not promise that learning history restores with a chat backup.

Native controlled tests demonstrate familiar-plus-new selection on both
platforms. Android's actual conversation row retains its selection through a
visible dwell and a readiness transition. Apple's isolated Simulator app uses
the real bundled starter/frame providers and playback controller. The actual
Listen control reaches playing and then ready; Japanese Latin readings and
mixed English/Swahili speech have retained receipts. These are simulator/emulator
checks with synthetic messages, not human acoustic acceptance or a claim that
every real conversation has a suitable mapping.

Apple's starter progression proof begins with a fresh synthetic vault, displays
**I → mimi**, and records the exposure from the real visible-dwell callback.
The subsequent message includes the familiar **I** and new **music → muziki**.
Encrypted-vault reopen is separately qualified with an injected test key; this
does not establish production keychain access or learning-history backup.

All 110 supported language directions now have short synthetic playback
completion evidence on both platforms. Apple Simulator reports no errors or
underruns. Android's offline foreground run reports no feeding underruns and
one terminal drain counter per direction. Its initial background test could not
obtain audio focus and is retained as a failed harness run. These checks prove
controller completion in the recorded environments, not human pronunciation
acceptance, physical-device performance or long-message behavior.

The exact-reference route now permits independently guarded candidates for
automatic immersion. Controlled Android QA exercised Japanese and Swahili,
including atomic phrases, full-reference output and concurrent source lookups.
The exact signed release APK also passed offline startup and onboarding checks
on a fresh API 34 x86_64 emulator: language selection, Japanese script/Latin
previews, Swahili, speed controls and the Listen UI transition. No sign-in was
attempted. The emulator had no audio output, so this is not acoustic evidence.
The existing accounts were untouched. See the
[signed release receipt](../qa/android/signed-release-20261116/receipt.json).

Automatic immersion still uses accepted local mappings. Newly measured Apple
and Android local translations of independently selected words include wrong
senses for ordinary ambiguous words. Those diagnostic outputs are not enabled
as automatic immersion. A generic exact Arabic reading database has also passed
an isolated Android lookup probe; it remains an inactive candidate, with no
reading for conflicting or unknown forms. Neither experiment establishes a
conversational coverage percentage.

The active-catalog reading audit found no emitting path that lacks the required
Latin reading for a non-Latin target. It covers current frame, starter, legacy
mapping and context data, with the native display gate remaining authoritative.
Punctuation in 35 authored sentence readings causes 468 target reference records
to abstain as whole units; independently qualified word/frame units can still
appear. This is a conservative availability limit, not missing-reading output.
The [audit](../qa/immersion/active-reading-audit-20261116/review.json) checks script
structure, not human pronunciation quality or future generated output.

The full Android APK and AAB at `0fda43f` are signed and verified, including all
1,077 packaged assets and the accepted 007 catalog. The specified ARM64 device
download estimate is **416,960,679 bytes**; this is a local bundletool estimate,
not Play acceptance. See [November 16 artifacts](../release/build-artifacts-20261116.json).
The earlier `a53ff86` signed artifacts remain historical.
Apple's device Release archive at `4908d4e` is built and verified: 103 actual
compile inputs, 583 immersion resources, 69 lexical resources, 367 speech
resources and 13 privacy manifests match the frozen inputs. It is unsigned and
must not be uploaded. No signing attempt was made.

The reviewed client source is now publicly available as the
[November 16 source preview](https://github.com/FallSoftCo/vipi-clients/releases/tag/source-preview-2026-11-16).
The 5,875-member archive binds to the current Android and unsigned Apple inputs.
Both public downloads were fetched anonymously and their hashes verified.
Source publication does not establish every linked dependency's combined-binary
distribution terms. See the [publication record](../release/client-source-publication-20261116.json).

The deployed service is now `742e119`, adding the public username invitation
page. Registration remains restricted to the owned review accounts. No new
provider generation, store upload, purchase or review submission occurred in
this continuation. Native browser inspection on November 16 reconfirmed Vipi
as a Play draft, App Store Connect at sign-in, and Google Cloud requiring
company reauthentication. The Mac signing/keychain hold remains in force.
The requested automatic-reset timer and policy remain disabled.

The sections below distinguish historical November 11 account evidence from
the current artifacts. Store forms, signed Apple runtime, billing, background
delivery and actual customer access still require qualification before submission.

## Product and active language data

Both native clients now activate the **007 directional dictionary increment**
on top of the accepted local vocabulary. It adds 71 reviewed directional patterns
and restricts 20 Italian noun contexts. All 110 language directions retain their
finite catalogs; English→Japanese and English→Swahili retain their original raw
starter providers. Unsupported text stays unchanged. Automatic switching makes
no translation or model-readiness call.

Actual bundled default qualification passed on both platforms: 19 positive
opportunities and 13 controls, with 10 intended automatic outputs, 17 direct
outputs and no forbidden control output. Abstentions remain recorded, including
the long Swahili phrase and Korean school example. These small authored checks
establish the tested routing and safeguards, not broad conversational coverage.
See [Apple qualification](../qa/immersion/directional-dictionary-007/apple/qualification.json)
and [Android qualification](../qa/immersion/directional-dictionary-007-android/receipt.json).

Earlier 39/264/304 emitting-case counts used the same 1,320 directed development
cases at different revisions. They are historical comparisons, not current
population coverage or accuracy. The corrected 005 content is now part of the
active baseline, not an unpromoted private candidate. Dictionary mining and
carrier experiments outside accepted catalogs remain research only.

The first-release priority is local single-word and short-phrase switching,
source-language grammar, Latin-letter reading guides and speech. **Explicit Full
translation is still present**, separate from automatic switching, and may need
model downloads. Its optional deferral has not been approved. ML Kit Translate
remains linked; Android's unused ML Kit language-ID dependency has been removed.
Local CLD2 detection can still abstain or be wrong. Reading guides and speech
availability are not claims of perfect pronunciation, fluency or mastery.

## Service and real account evidence

The production WorkOS application is active for two owned review accounts;
public registration remains closed. Restricted staging has subscriptions
unenforced. Both accounts completed Android native authentication, profile
creation and separate encryption-key enrollment. Exactly two synthetic native
messages were exchanged, decrypted to their original text and marked Delivered.
This is foreground human-chat evidence, not public onboarding, purchases,
background push or Apple live authentication qualification.

The service runs `742e119`, preserving the earlier `b97b2c9` public vBot
guardian-consent terms and adding username invitation pages. Its two owned reviewer accounts have explicit
complimentary Base and Bot mini access, with no purchase, expiry or trial invented.
The Android app verified both review-access labels against the live service.
The API was updated without changing the database/schema, push or shared services.
A database-local restore HOLD blocks normal access to marked copies, qualified
with SQLite and an isolated PostgreSQL/asyncpg instance. The live database is
unmarked. External restore integration and authoritative financial replay remain
unfinished; no restored service is authorized to reopen. See the
[deployment receipt](../qa/backend/service-recovery-r01/deployment-r01.json).

The scoped APNs worker is active with the retained production credential.
Actual APNs device delivery remains unqualified; a production credential does
not qualify development-sandbox delivery. FCM remains unconfigured. The DeepSeek
bot provider is configured with a dedicated company credential. One normal
Android request received a real response in 2.353 seconds, with allowance changing
from 150 to 149 and its reservation settled. This single result is not typical
latency or broad response-quality evidence. An earlier request failed before
provider reservation because both clients omitted device credentials; both
clients now attach the existing registered credential, preserve drafts when it
is missing, and never automatically resend an uncertain request. The earlier
request remains preserved and was not retried. See the
[actual Bot result](../qa/android/bot-live-r02/receipt.json).
Public help/privacy/terms routes are live. See
[reviewer access](../qa/backend/reviewer-access-r01/live-activation/deployment.json)
and [provider configuration](../qa/backend/bot-provider-configured-r01/receipt.json).
Relevant evidence:
[production authentication](../qa/backend/production-auth-staging-r01/receipt.json),
[native Android authentication](../qa/backend/native-production-auth-android-r01/receipt.json),
[two-message exchange](../qa/backend/native-peer-chat-android-r01/receipt.json), and
[APNs worker configuration](../qa/backend/apns-worker-configured-r01/receipt.json).

Account-bound **Sign in again** and device-replacement recovery are separate.
Scoped native recovery checks passed; Apple's unsigned synthetic-session checks
do not establish live OAuth or keychain persistence. Ordinary saved-chat access
must not be confused with restored server credentials.

## Release artifacts, source and stores

Current Android release artifacts bind to `0fda43f`; the unsigned Apple device
archive binds to `4908d4e`. Published source preview r10 was frozen at `dbe2cfb`
and its application inputs match both artifacts. Android's signed bundle passes
source, configuration, notice, signature and 16 KiB alignment checks. Its
specified ARM64 download estimate is 416,960,679 bytes; Play has not measured or
accepted it. See [current artifacts](../release/build-artifacts-20261116.json).

The earlier signed Android startup check stopped before installation because
the existing production package contains Alpha's encrypted account/history under
a different signer. November 16 qualification instead used a new isolated
emulator and the exact signed APK. No existing package or account was erased;
the isolated emulator is now stopped.

Apple's November 16 device archive verifies the compile inputs and resource
counts above. Inherited uncommitted experiments remain excluded. The archive is
unsigned and nondeployable under the existing signing/keychain hold. Both
keychains were still locked in the November 16 read-only check. No signing,
export or provisioning attempt was made.

Source preview **r10** contains the native clients, build tools, language data,
license notices and 577 retained upstream source archives. All 5,875 members
were independently checked against the recorded file inventory; the public
archive SHA-256 is
`b6e34c24befaf58232ff7b78e39f71478e555bbf18c535dbc9810831c3edcead`.
The source review inventories its binary/text exclusions and is not an exhaustive
security or license certification. Superseded r08 archive bytes were retired
after replacement checks; metadata and original inputs remain. See
[client build instructions](../CLIENT_SOURCE.md).

No store build upload or review submission has occurred. Apple has a private
app record and separate annual products: Base $12 and optional Bot mini $48 in
the US, each with its own one-month trial for eligible subscribers. Configuration
is not a completed transaction. Google Play private app `4975664610567218322` now exists as **Vipi** under
Fallible Software, Co. Its text, Communication category, support contact and
privacy URL are saved. The icon, feature graphic and two actual Android chat
screenshots are also saved, Latin letters first. All ten app-content declarations
are complete, including both reviewer accounts, the 13+ audience and Data Safety.
The console shows none needing attention. No subscription products exist yet: the console requires
an app bundle upload before allowing their creation. See
[Apple configuration](../release/apple-store-configuration.json),
[Android review preparation](../release/ANDROID_STORE_REVIEW.md), and
[submission checklist](../release/STORE_SUBMISSION.md).

## Remaining release work

- Restore Apple company authentication/signing access, then complete signed
  runtime/export qualification. Current unsigned archive must not be uploaded.
- Resolve the exact linked-SDK distribution basis or the pending product-scope
  choice. The ML Kit/AGPL question is dependency-specific; Signal's store presence
  is neither blanket permission nor a blanket prohibition. Billing/Play terms
  remain separate. Do not remove optional features without approval.
- Complete FCM configuration and real background delivery, store purchases,
  renewals and restoration. One Bot response/allowance and complimentary reviewer
  access now pass; these do not qualify ordinary paid customer access.
- Reconcile store metadata, privacy disclosures, current screenshots and actual
  release artifacts before any declarations, upload or submission. Use the
  corrected [export assessment](../release/EXPORT_ASSESSMENT.md); do not reinstate
  obsolete blanket BIS source-email, CCATS or annual-report assumptions.
- Continue practical vocabulary/sense review and document remaining detector,
  reading, accessibility and acoustic limits. Do not replace these with a
  percentage inferred from reused authored or training inputs.

## Workspace and test authority

Canonical source is `/home/ai/Development/vipi-production-20261107`, branch
`delivery/production-20261107`. New Apple work belongs on native
`apple@macbook-pro`; Android uses the existing QA emulator on system76. The iPad
is reserved for 8bar Club. Do not recreate the retired Apple VM or use retired
OZZZ hosts. Preserve unrelated native projects, accounts and shared services.
See [build environments](BUILD_ENVIRONMENTS.md) for established routes.
