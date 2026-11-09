# Apple background inbox hint

The APNs provider sends `kind: inbox_changed`, but Apple's background notification callback checked `type`. The callback now reads the actual provider field. Its default asynchronous operation still calls `PushNotifications.shared.inboxChanged()`; a test-only initializer permits checking the real delegate callback without a network account.

The shared JSON fixture is checked against the actual backend APNs request builder in both sandbox and production environments using an ephemeral signing key and an HTTP mock transport. All nine backend push tests pass. No live provider is called. Payloads contain only a generic notification and inbox hint, with no conversation content or identity.

The native iPhone simulator build passes with two compiler jobs. Both callback tests pass: the backend fixture invokes synchronization and returns each fetch result, and unrelated, incorrectly typed or legacy-key-only payloads do not fetch. The build took 35.38 seconds and the test command 9.94 seconds. Source verification covered 648 files and pinned dependencies. Existing app preferences were restored, the owned app stopped and both Mac immersion labs preserved. The iPad was not used.

This establishes the provider/client payload contract and compiled callback behavior. It does not establish OS background scheduling, permission recovery, real APNs delivery or a signed store release. Exact source and retained private evidence hashes are in `receipt.json`.
