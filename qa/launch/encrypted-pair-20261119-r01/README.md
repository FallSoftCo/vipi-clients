The launch pair harness extends the existing `NetworkMessagingTests` and
`NetworkMessagingDeviceTest`; it does not substitute plaintext, a fake cipher,
or a mock relay. Current source is based on 6f1cf0a3. A fresh native execution
is still pending the existing Android and Mac owners' resource handoff.

Run `scripts/serve-isolated-native-pair.py` with the existing backend Python
interpreter, a NEW NVMe run directory, and a private JSON array of the two
verified QA subjects (raw legacy `user_…` or canonical shared
`fallsoft-vipi-production:user_…`). The existing pinned dual-authority verifier
accepts both; using a legacy fixture does not migrate it or establish new shared
user sign-in proof. The service
uses current real WorkOS JWT verification, an exact two-subject allowlist and
fresh SQLite storage, binds only 127.0.0.1:48944, and stops after at most 30 min.
It never reads provider admin, push, store or AI credentials from VIPI_* env.
Use an owned Mac SSH loopback forward and an owned Android ADB reverse; remove
only those forwards at completion. Do not run the retired OZZZ server launcher.

Use existing OWNED QA native sessions; do not copy keychain dumps, create a
WorkOS user, replace another user's session, or use the prohibited
qa/macos/apple-resume-20261116-r01/keychain-raw.json. Per-device private
network-config.json contains `run`, `username` (unique vqa_ name, 3–24 chars),
`peer`, `endpoint` (http://127.0.0.1:48944), `expected_subject` (raw user_ ID),
`use_existing_session:true`, and `isolated_fresh_profile:true`. Android also
requires `vipiLiveNetwork=true` and `vipiUseNativeSession=true` instrumentation
arguments. These new profile/device registrations affect the isolated database
and newly allocated local account vaults only.

First invoke `testInspectOwnedSessionWithoutExportingCredentials` on iOS and
`inspectOwnedSessionWithoutExportingCredentials` on Android. Read only their
network-session-readiness.json artifacts: presence, expected-subject match and
saved authority; no credentials or keychain bytes are exported. A mismatched or
absent session requires an owned-account sign-in, not token transplantation.
Fresh profile creation also requires real authentication within ten minutes;
a refresh of an old session does not satisfy this server policy.

Invoke these existing native stages individually, once each:

1. Android `publishAndroidKeys`.
2. iOS `testPublishAndSendToAndroid`.
3. Android `receiveSwiftAndReply`.
4. iOS `testReceiveAndroidOutOfOrderAndRestoreSession`.
5. Android `verifyDeliveryAndRestoreSession`.

The authored original text, including Unicode, crosses real backend HTTP as
libsignal ciphertext. Each side reopens its durable queue before first POST,
checks unchanged message ID and ciphertext, receives originals, acknowledges
only committed receives, and checks duplicate sends and empty inboxes. Swift
receives Android's replies in order 2,0,1. Queued-without-transport/reopen is
covered; actual network-loss timing and OS process termination remain separate
journeys. Reusing an existing sign-in is not new hosted signup UI proof.

Local verification: 38 backend tests passed, 1 skipped (optional live-provider
case), including invitation association bodies, real JWT signature authority
boundaries, shared-link preservation, free-link no-trial behavior, contentless
push requests with controlled provider transport, and settings isolation. Real
loopback smoke r02 passed health 200, unauthenticated me 401, invitation 200 and
both association 200, then graceful server exit 0 and closed-listener readback.
No authenticated native pair run, PostgreSQL concurrency, APNs/FCM delivery,
notification permission behavior, local immersion privacy or sign-up UI is
newly claimed by these checks. Those need their own bound native receipts.

Public read-only checks on 2026-11-20 UTC found invitation 200 but both
/.well-known/apple-app-site-association and /.well-known/assetlinks.json 404.
Candidate public_pages.py already serves correct scoped association JSON,
validated through real local HTTP. Candidate nginx forwards all / paths to the
API. Production requires those exact routes delivered by the active backend
release (or scoped static nginx aliases); no client-only change fixes 404.
Live readback confirms /opt/vipi/current resolves to
/opt/vipi/releases/full-message-pages-20261119-r01. Its exact module at
deps/vipi/public_pages.py has SHA256
328722fe4e4314db7fd5ca3c4a10da132ef106049bba3a223b3aa2c4f5277095
and lacks both routes; direct loopback upstream returns 404. The minimal
association-only.patch changes just the JSONResponse import and two GET routes,
with no schema dependency. Reconcile that exact preimage before packaging a
new immutable release and manifest/RECORD. Local comparison confirms the root,
privacy, terms, help and invitation responses retain exact bodies AND headers.
No production deployment, reload or duplicate external submission occurred.

Authentication: public discovery reconfirms the existing shared Vipi client
client_01M7N9Y2DGSJJVT1ZV6TY7DTZ4 uses the Fallsoft environment key authority
client_01JPK69ZZFHH0NSP8BY2HGRDX6; separate legacy Vipi client
client_01M6VYVQQ9GWVNS95DFGABXEW9 has its own key authority. Existing native
records bind saved sessions and refresh tokens to the original authority;
explicit dual-proof linking preserves the Vipi UUID/device/keys. The Swift
network fixture now retains that saved authority when forcing token refresh.

Safe branding proposal: customize ONLY the already-created Vipi application
app_01M7N9Y2DGDVFNZBXCB3SAEFZX in the shared Production environment. Use Vipi's
logo/display name and https://api.mambovipi.app/{terms,privacy}; keep the two
existing Vipi callbacks, audience, users, upstream Google/Apple connections
and saved sessions. WorkOS supports application-specific hosted UI and email
branding while sharing users; this avoids a directory switch or duplicate app.
Preserve environment/default-app branding. Dashboard inspection and a reviewed
application-specific diff precede any save; no settings were changed here.
See https://workos.com/docs/authkit/branding,
https://workos.com/docs/authkit/applications and
https://workos.com/changelog/custom-branding-per-application.
