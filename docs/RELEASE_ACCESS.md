# Release sign-in and credential recovery

Use your existing desktop account on system76 and your native Mac account.
These procedures let you work with saved sign-in sessions and signing inputs.
For an expired or revoked session, finish the vendor's own trusted-device,
passkey, or recovery prompt. One owner can operate both consoles and both
test phones. Keep the two messaging QA accounts separate.

## Check access before a release

| Work | Routine path | If access expires |
| --- | --- | --- |
| Private Git | Use the existing private origin and your configured SSH key or credential helper. Check the exact release ref with `git ls-remote origin <ref>`. | Unlock the existing key in your key agent or renew your Git login in the official browser flow. Recheck the remote account and private repo before pushing. |
| Native Mac | Use the signed-in Xcode account and its login keychain. In Terminal, `security find-identity -v -p codesigning` lists usable signing identities. | Open Xcode Settings → Accounts under your native Mac login. Refresh that account and its profiles. Use Keychain Access to check the intended identity and unlock your login keychain if macOS asks. |
| App Store Connect | Open the Vipi record using the owner browser profile and its existing session. Check the team, current builds and review status. | Use the Apple sign-in prompt and your trusted device when asked. Reopen the same app and team afterward. |
| Play Console | Open the Vipi record from your normal signed-in browser profile on system76. Check the account, app ID and intended track. | Choose the saved owner account and use your Google passkey or security key if enrolled. Complete any Google recovery prompt on the official sign-in page. |
| Android signing | `python3 scripts/build-android-release.py --check` checks local paths and permissions. A normal release build uses those files without asking for the signing passwords. | Update only the affected local signing input as described below. Keep the existing upload certificate until a verified Play upload-key reset requires a change. |
| Shared production host | Use the existing pinned SSH admin route for authorized observations. For a change, check the current human enrollment and receiver receipt first. | Identify whether the local agent, request, or enrollment expired. Follow [Shared-host release access](#shared-host-release-access). |

Check store status by reading it back before another action if a session
expired during an upload, review change, or rollout. Never copy browser
cookies, keychain contents, MFA seeds, device codes, or provider tokens into
a repository, a release record, or another browser profile.

## Shared-host release access

The November 27 review verified a workstation sender and a disposable receiver.
Production enrollment and an installed human receiver still need a custodian's
receipt. The sender's `authenticated_offline_only` result records local review.
Look for the original target receipt before treating any change as accepted.
[Sender guide](https://github.com/FallSoftCo/infrastructure/blob/cd703a20399587bae8e1fcbacc310dfad682349a/services/vipi-relay/ops/human-maintenance/README.md) · [Receiver qualification](https://github.com/FallSoftCo/infrastructure/blob/7d251cc8d884df2902b143aefd9e80c5ed63bef0/services/vipi-relay/ops/human-maintenance/RECEIVER-FIXTURE.md)

**First enrollment.** The authorized host custodian verifies your identity through
an independent channel and records your personal public-key fingerprint, actual
workload delegations, validity and roster revision. One person can hold several
roles, with one entry in the roster. Other affected owners acknowledge their scope
or provide a verified delegation. The receiver fixture covers whole-host owner confirmation and refuses scoped
proposals. The custodian must qualify the human intake against the installed
registry and applicable scope policy under the shared lock and verify a durable
target receipt. Each application operation also needs its own mode
clearance. Use the [deployment runbook](HUMAN_RELEASE.md#deploy-through-the-human-host-workflow)
for that sequence.

**Routine access.** Set `VIPI_HUMAN_PUBLIC_KEY` to the public `.pub` file in
your approved case profile. Run these read-only checks in your personal terminal.

```sh
ssh-keygen -E sha256 -lf "$VIPI_HUMAN_PUBLIC_KEY"
ssh-add -E sha256 -l
```

Compare the first fingerprint with the custodian's current enrollment, then
find that same fingerprint in the second command's output. A match means the
agent lists the selected key. Its keychain or hardware policy may still ask
for approval when you sign.

| What you see | What to do |
| --- | --- |
| Agent unavailable, empty, or missing the expected key | Reconnect to your existing agent or unlock the enrolled key in its usual vault. Repeat the fingerprint check. The same key keeps its enrollment. |
| Different enrollment fingerprint, revoked key or expired workload delegation | Have the custodian verify the replacement or renewal and publish the current roster and case pins. Keep the original evidence. |
| Request expired or connection lost around submission | Read the target's original intent, registry state, event and terminal receipt first. A pending intent stays with the custodian for reconciliation. After confirming the command had no effect, use a fresh state export and sign a new request if the action is still required. |

## Apple and Google

New browser, device or account-recovery events may require a password, a
trusted-device approval, or a verification code. Use the vendors' own
credential manager or security settings for passkey enrollment and recovery.
Role, agreement, and distribution-key changes still have to be accepted in the
owning console. Use the existing Xcode account and distribution signing
identity before considering certificate replacement. A profile can be renewed
on its existing certificate when Apple permits it. Confirm the App ID, team,
push entitlement and extension signing after refreshing it.

- [Apple Developer account recovery](https://developer.apple.com/help/account/access/resolving-access-issues/)
- [Xcode signing identities and account synchronization](https://developer.apple.com/documentation/xcode/sharing-your-teams-signing-certificates)
- [Google passkeys and security keys](https://support.google.com/accounts/answer/13548313)

## Android signing

```sh
python3 scripts/build-android-release.py --check
python3 scripts/build-android-release.py
```

The first command verifies the presence, ownership and permissions of input
files. The second reads the signing values into the existing Gradle build
environment and runs the production release checks and bundle task. It needs
your normal Android SDK and JDK settings. It prints no signing values and
performs no upload. Confirm the resulting certificate and bundle before using
it. See the [Android artifact verification](ANDROID_MAINTAINER.md#build-and-review-the-store-artifact).

The current default signing manifest is
`~/.local/state/vipi/android-signing-20261107/release-input-paths.json`.
It contains four keys, `store_file`, `store_password_file`,
`key_password_file`, and `key_alias`. The first three entries are absolute
paths. The registered Firebase app configuration is at
`~/.local/state/vipi/firebase-20261107/google-services.json`. Keep these
inputs outside Git, owned by your account, as mode-0600 files in mode-0700
directories. Keep your existing protected backup and recovery copy. The
launcher uses those files as-is. It creates no second password store.

When an input changes, put the replacement in a new private directory and
point a copy of the manifest at the new files. Copy material directly from
your approved recovery source. Keep signing values out of command arguments,
terminal output and shell history. Both `--check` and the build accept
`--signing-manifest /absolute/path/to/manifest.json` and
`--firebase-config /absolute/path/to/google-services.json`. Check the staged
replacement, build locally, and verify the signer and Firebase app before
making the new paths your routine defaults. Keep the old manifest and
original evidence for recovery until the replacement is proven. For a
genuinely lost or compromised upload key, use the owning Play Console reset
procedure and wait for confirmation before using a replacement key. The
Play-held app signing key and the local upload key have separate lifecycles.
