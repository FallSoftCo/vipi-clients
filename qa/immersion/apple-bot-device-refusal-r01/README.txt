Exact backend device_revoked refusal is rejected; no other error is reclassified. Rejected messages display Request not accepted and reconnect guidance, with no automatic resend. The attempted outgoing message remains saved and draft clearing is unchanged. Missing local registration still returns before persistence/draft clearing.

Native actual-source Swift probe covers exact refusal, unknown error, timeout, reopen/refresh/send no replay, device arguments and local credential failures. Uses in-memory MessageVault and synthetic ChatTransport; no encrypted disk, HTTP, provider, authentication or Keychain proof. Canonical XCTest regression updated but not run under the Keychain hold.

Final app compile source frozen at 287ae41; integration receipt binds exact revision, 1064 Git source hashes and generated compile inputs. No release archive, launch, signing, install or submission.
