# Native Mac development qualification — signing held

Reconciled November 9, 2026. This is a failed development qualification, not a
release artifact, store upload or successful translation demonstration.

The existing Mac was registered once under the Fallible Software Co team. A
development profile for that Mac alone was generated, downloaded and installed
with matching hashes. These completed portal actions must not be repeated.

A separate private source copy was reconciled against commit
`69b6583d1079fc8a8884822dd1fc3ccbedb82aef`: 622 canonical files matched. Its
opt-in harness would exercise the actual Swahili ML Kit path on iOS-on-Mac using
six authored English/Swahili inputs. It is not connected to customer routing.

Preparation passed. The two-job build reached signing, then exited 65 after
95.58 seconds with `CodeSign Vipi.debug.dylib: errSecInternalComponent`.
Read-only inspection found the login keychain locked. A separate existing
`pbtv58` keychain dialog had unknown ownership and was left untouched.

The owner explicitly retained the signing/keychain hold during operator
recovery. No further signing, unlocking, profile creation or launch is authorized
by this receipt. Continue independently available simulator and Android work;
reconcile a genuine dependency change before resuming signing.

No app launch, model download, translation capture, upload or submission occurred.
The iPad was not used. Existing native language labs remained running.

Private evidence: `investigations/vipi-ios-on-mac-20261109-r01/` contains the
staging manifests, `signing-block-r01.json` and retained build receipts/log.
The retained build log SHA-256 is
`dfa47eeffb16acb7c3f98b0de850444379abc03d43c9d02212545c74b25fc898`.
