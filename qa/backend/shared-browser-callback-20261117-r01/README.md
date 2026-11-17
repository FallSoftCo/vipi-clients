# Shared HTTPS browser callback qualification

After the shared-identity deployment, root completed one distinct production HTTPS callback flow with the owned company Google account using native Mac Chrome. Actual shared AuthKit displayed Google and Apple choices. Google sign-in returned to the Vipi-only confirmation page; root selected Cancel and observed that the account was not deleted. The destructive confirmation was never clicked. The owned browser window closed and the existing desktop/browser state was preserved. Screenshots remain private; this source proof contains no email, account identifier, token, authorization code or request URL.

An independent read-only backend check at 22:25:05 UTC found nine users, no changed authentication floors, and zero identity-link, account-deletion, global-deletion, trial-eligibility or billing-binding records. These aggregate counts equal the cutover/prebrowser baseline. This is evidence of no new durable account/business ledger operation, not a complete transaction audit; browser rate-limit counters are outside that comparison. The verifier did not repeat sign-in, callback, Cancel or the deletion-page GET, and did not read request logs.

Both nginx API server blocks have access logging disabled, and the actual Uvicorn service uses `--no-access-log`. Nginx critical error logs and Uvicorn warning/error logging remain enabled. Configuration inspection does not establish that secret-bearing failure records can never exist; no error/request log content or request URLs were queried.

This supersedes the deployment record's pending HTTPS callback gate for this single Google confirmation-and-Cancel path. It does not qualify Apple browser sign-in, destructive deletion, global deletion, identity linking, purchase restoration or unrelated release gates. The successful native public PKCE and native confidential code-exchange proofs were not replayed.

`backend-postcheck.json` records the sanitized counts, configuration checks and the root-owned native receipt hash. The actual native UI observations are attributed to root; the database/configuration postcheck is independent.
