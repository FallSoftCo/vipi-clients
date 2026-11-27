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
| Shared production host | Use the existing pinned SSH route through your unlocked personal key agent. Use the enrolled human change credential for maintenance. | Reopen the personal key agent and verify the original key and host identity. If the human change key needs renewal, use the custodian's versioned roster and rotation procedure. A working SSH connection alone grants no application change. |

Check store status by reading it back before another action if a session
expired during an upload, review change, or rollout. Never copy browser
cookies, keychain contents, MFA seeds, device codes, or provider tokens into
a repository, a release record, or another browser profile.

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
