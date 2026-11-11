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

The latest unsigned Apple archive from `56e0120` is **diagnostic**: exact
committed-source qualification failed because seven inherited Swift files were
included. They are being preserved outside the build; a corrected archive is
pending. Successful compilation and verified catalog/notice assets do not turn
that artifact into a source-qualified or signed release. The signing/keychain
issue remains unresolved. Earlier signed Android and unsigned Apple release
artifacts also do not qualify the current complete release inputs.

Private corresponding-source candidate **r06** at `56e0120` passed streaming
manifest/member and committed-input verification. It has not been published and
predates subsequent source changes. It is not proof that the diagnostic Apple
archive corresponds exactly to it. Private receipts are retained under
`investigations/vipi-submit-20261110-r01/apple-unsigned-release-r02/closure.json`
and `client-source-final-preparation-r01/final-handoff.json` in that same
investigation root. [CLIENT_SOURCE.md](../CLIENT_SOURCE.md) describes the portable
source closure; final release changes still need reconciliation.

No store build upload or review submission has occurred. Apple has a private
app record and separate annual products: Base $12 and optional Bot mini $48 in
the US, each with its own one-month trial for eligible subscribers. Configuration
is not a completed transaction. Google Play app creation and its Developer
Program Policies/export declarations remain unsubmitted. See
[Apple configuration](../release/apple-store-configuration.json),
[Android review preparation](../release/ANDROID_STORE_REVIEW.md), and
[submission checklist](../release/STORE_SUBMISSION.md).

## Remaining release work

- Finish the corrected source-bound Apple archive, then signing and final
  artifact/source reconciliation. Retain diagnostic archives as such.
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
