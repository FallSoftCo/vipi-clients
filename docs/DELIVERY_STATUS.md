# Current delivery status

Updated 2026-11-11. Vipi remains restricted staging, not a submitted or publicly
available store release. This page describes current operational state;
[VERIFICATION.md](VERIFICATION.md) and the linked receipts retain historical
experiments, failures and qualification limits. The longer prior status remains
in Git history before this revision.

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

The service now runs `2796f70`; the API and existing push worker were updated
without changing the database/schema, configuration or shared services. A new
database-local restore HOLD blocks normal access to marked copies, qualified
with SQLite and an isolated PostgreSQL/asyncpg instance. The live database is
unmarked. External restore integration and authoritative financial replay remain
unfinished; no restored service is authorized to reopen. See the
[deployment receipt](../qa/backend/service-recovery-r01/deployment-r01.json).

The scoped APNs worker is active with the retained production credential.
Actual APNs device delivery remains unqualified; a production credential does
not qualify development-sandbox delivery. FCM and the DeepSeek bot service remain
unconfigured. Public help/privacy/terms routes are live. Relevant evidence:
[production authentication](../qa/backend/production-auth-staging-r01/receipt.json),
[native Android authentication](../qa/backend/native-production-auth-android-r01/receipt.json),
[two-message exchange](../qa/backend/native-peer-chat-android-r01/receipt.json), and
[APNs worker configuration](../qa/backend/apns-worker-configured-r01/receipt.json).

Account-bound **Sign in again** and device-replacement recovery are separate.
Scoped native recovery checks passed; Apple's unsigned synthetic-session checks
do not establish live OAuth or keychain persistence. Ordinary saved-chat access
must not be confused with restored server credentials.

## Release artifacts, source and stores

The retained native release artifacts bind to committed app source `6ceaf4b`.
They are superseded for submission by the new complimentary reviewer-access
model and copy; updated native qualification is underway.
Android's private signed bundle passed signature, production configuration,
language data, notice and 16 KiB alignment checks. Its device-specific ARM64
download estimate is 416,946,355 bytes; Play has not measured or accepted it.
The corrected Apple device archive passed actual compile-input and packaged
asset verification. Seven inherited Swift experiments were preserved outside
its inputs. It remains unsigned, nondeployable and subject to the existing
signing/keychain hold. Earlier diagnostic archives are superseded.

Private source package **r07** matches the same app revision; all 5,840 archive
members were verified. It is not published. Superseded r06 archive bytes were
retired after replacement verification; its metadata remains. See
[current artifact records](../release/build-artifacts-20261111.json) and
[client build instructions](../CLIENT_SOURCE.md).

No store build upload or review submission has occurred. Apple has a private
app record and separate annual products: Base $12 and optional Bot mini $48 in
the US, each with its own one-month trial for eligible subscribers. Configuration
is not a completed transaction. Google Play private app `4975664610567218322` now exists as **Vipi** under
Fallible Software, Co. Its text, Communication category, support contact and
privacy URL are saved. The icon, feature graphic and two actual Android chat
screenshots are also saved, Latin letters first. Privacy URL, five factual
content declarations and IARC content ratings are complete. Sign-in details,
target audience and Data Safety remain. No subscription products exist yet: the console requires
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
- Complete provider configuration and actual background delivery, Bot mini
  responses/allowance, purchases/renewals/restoration and store reviewer access.
  Existing staging exemptions do not qualify paid customer access.
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
