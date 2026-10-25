# Decisions and discovery — 2026-10-24

## User decisions

- Product Vipi; bot contact vBot; add-on plan Bot mini. Avoid “AI” as the plan/feature marketing name while accurately disclosing the provider and processing.
- Separate native apps; no custom shared immersion engine. No lesson model.
- Core immersion UX must be demonstrated across ten major languages and all 90 directed pairs on each native app. Transliteration is mandatory for non-Roman immersion, in the default in-place display; original script stays accessible. Audio is the pronunciation experience; no IPA/phonetic glyphs in chat. The earlier optional-transliteration wording was explicitly corrected by the user.
- Text-first, one-to-one, local immersion/translation/speech. Prepare for later media/groups.
- E2EE human messaging; client-owned history/backups; 72-hour delivery expiry.
- Annual base and light bot plan only, one-month store free trials. Earlier $1/year/web-only proposals are superseded.
- AWS supplies domains. Existing small Hetzner host may run the backend.
- User approved `mambovipi.app` and open-source clients on 2026-10-24. AWS registration succeeded; one year, $20 current registration/renewal price, auto-renew enabled. Company contact reused from the existing company domain, with contact privacy enabled. No credential or contact details belong in source.
- Use Mobbin and Built for Mars throughout; test through existing emulators/simulators/environments; submit both stores after proof.
- Preserve unrelated OZZZ/Enterprise work and other services.

## Environment

Owner thread: `01a16e0d-ac69-7dd0-872a-8cf087160515`. New source workspace only; existing copied Osmos repositories are read-only references until their migration receipts are inspected.

Linux: OZZZ-OS (`ozzz-aosp`), Android SDK `/aosp/ozzz-android-toolchain/sdk`; use disk-backed storage and measured `storage-build` admission. Latest CPU free-space floor is 8 GiB per user override. Mac: `apple@macbook-pro`, Xcode 26.6, xcodegen, company signing identity. Existing running test devices belong to other work; provision a dedicated Vipi test device before changing applications/state.

Fleet inventory currently lists existing `8bar-app` and `rjuniyer-chat` cloud projects; other known SSH hosts include `ozzz-app`, `revenue-sleuth` and `rjuniyer-live`. Inventory coverage is explicitly incomplete account-wide. No target is selected, and no host changes have occurred.

## Design references

- Mobbin WhatsApp onboarding: https://mobbin.com/flows/550ae0b8-7e2c-46d7-a85e-ecf39674c399 . Reference retrieved; detailed screenshot inspection pending. Do not copy visual assets or claim findings from images not inspected.
- Built for Mars contextualising dates: https://builtformars.com/ux-bites/contextualising-dates . Use actual dates for trial/renewal clarity.
- Built for Mars contextual defaults: https://builtformars.com/ux-bites/contextual-default-options . Prefill the known language from device preferences but let the user correct it.
- Built for Mars alternative routes: https://builtformars.com/ux-bites/citymapper . Provide a useful path while downloads are pending.

These sources are analogies, not evidence that immersion improves acquisition. BFM's initial synthesis suggested tooltip overlays and a fixed 30-day trial; Vipi instead retains the user's in-place reveal requirement and the stores' actual calendar-month dates.

## Open technical decisions

1. Qualify official libsignal native bindings instead of the older OMEMO/Signal-C adapter. Pin 0.105.0 on both platforms (the version pinned by Signal-iOS when inspected), iOS archive SHA-256 `556a82414b545490085a0e21d94990788bdcbee4d769043f7889397872443faf`, source revision `4beb029d8a941f81e7d9c6d8af1ed25a677569a8`. Open-source clients are approved; preserve AGPL source/license obligations and review actual store distribution terms. Upstream use outside Signal is unsupported. Synthetic-key interoperability tests do not establish production key-store safety.
   - Native Android → Swift → Android exchange passed, including out-of-order replies and replay/tamper rejection. Keep libsignal as the implementation candidate.
   - Distribution qualification remains open, not a demonstrated prohibition. Current libsignal is AGPL-3.0; the explicit App Store permission in the old C library is absent. Signal's 2016 statement supports compliant open-source App Store apps. Upstream issues 684/691 have no maintainer determination. Signal's own App Store presence does not establish downstream licensing terms, but an unanswered issue likewise does not prove incompatibility. Do not change libraries solely on that issue or represent it as an established blocker. The user challenged the earlier overly definitive wording, which was corrected.
2. Relay expiry implementation: stock ejabberd behavior must be measured; transport acknowledgement is not application durable receipt.
3. Alignment quality and launch language coverage: full-text native translation does not supply word alignment. The local conservative pipeline needs evaluation across contexts and scripts.
4. Host capacity and final static pack provider. Domain choice resolved: mambovipi.app.
5. Exact store price points and practical Bot mini allowance established from provider usage measurements.

## Primary technical references

- https://github.com/tigase/Martin
- https://github.com/tigase/MartinOMEMO
- https://www.igniterealtime.org/projects/smack/
- https://github.com/signalapp/libsignal (upstream explicitly does not support use outside Signal)

Refresh references and pin exact revisions during the implementation spike; a current package name alone is not a security qualification.

## Implementation findings

- WorkOS Vipi staging app is isolated from existing application configuration. Public client ID `client_01M5QPQSVXQDEJGQ1CYZ75MSGS`; callback `co.fallsoft.vipi://auth/callback`. Native Swift 0.8.0 and Android 0.4.0 SDKs use PKCE; no API keys ship in clients. Production configuration and actual sign-in/refresh/revocation proof remain pending.
- Apple documents that Translation does not run in the iOS simulator. Simulator UI proof is separate from translation proof. Android ML Kit 17.0.3 passed an actual dedicated-emulator test: model preparation, both network radios disabled, no active network, three synthetic sentences translated into Spanish.
- The first alignment engine is conservative dictionary corroboration against whole-text translation, not a general semantic word aligner. Its three-word sample is an onboarding illustration, not a downloadable language pack. Broad language quality is unproven.
- Dedicated QA devices: Android `vipi-api35-20261024`, serial `emulator-5620`; iOS `Vipi iPhone 17 20261024`, UDID `46CB569D-EA59-40E3-82CC-F4A0F36EDB87`. Other sessions' devices are unchanged.
- Mobbin chat screens inspected: https://mobbin.com/screens/d86a287d-ead3-48e2-b09f-1066ce33b280 and https://mobbin.com/screens/bf072681-6397-4170-b8be-4fc8c291231f . Single message bubbles, quiet controls and familiar conversation hierarchy inform the original native UI.
- BFM critique applied to the implemented welcome: demonstrate immersion before asking for an account, keep meaning one tap away, and use clear native-language instructions. Additional promotional links and overlays were omitted to retain the user's minimal UI.

- 2026-10-24 owner correction: every Vipi store/provider account must belong to FallSoft.Co / Fallible Software. Jeane LLC is not the correct Google Play developer account; do not create or publish Vipi there. The owner also explicitly authorized autonomous interaction with the attached, unlocked iPad while away, including native QA and required language-download prompts.


## Identity isolation correction — 2026-10-25

Application-specific redirects/API credentials do not isolate the WorkOS user pool. The existing Vipi staging application shares users with Fallible Software's default application. Never enable provider-wide account deletion there. Vipi now has a separate project and free staging environment (`environment_01M5S2CDCTMYJ46EBGXYWS5KBC`, public client `client_01M5S2CDSQ8F7FEX26G3CY9VS1`). Complete hosted sign-in/refresh/reauthentication and synthetic lifecycle qualification before changing deployed configuration. No existing user/environment was transferred. Production remains unconfigured. Account deletion is implemented with a durable capability and leased provider cleanup; a shared-pool configuration fails closed.

Real dedicated-provider lifecycle and hosted sign-in/reauthentication now passed; see VERIFICATION.md. The browser deletion route is implemented and qualified with a synthetic provider. Keep the current public service and native client configuration unchanged until the coordinated, reviewable cutover is ready. Do not claim a functional public web deletion URL merely because its callback was registered in WorkOS.
