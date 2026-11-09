# Production WorkOS provider lifecycle

On November 9, the dedicated Vipi production environment passed real password authentication, existing backend JWT verification against its pinned JWKS, public-client refresh without an API key, refreshed-token verification, and session revocation followed by a rejected refresh (`invalid_grant`). The refreshed token rotated. The exact tagged disposable fixture was deleted and absence verified.

The fixture was provisioned by an administrator with a generated password and its email marked verified. This does not qualify email delivery, hosted native PKCE/callback behavior, signup, recovery, or live production API cutover. No application service, live database, allowlist or authentication setting changed. Existing access JWTs are locally verified until expiry; a rejected refresh does not establish immediate rejection of every already-issued token.

A first local preflight rejected an over-specific API-key prefix before any provider request; that failed script and its correction are retained privately. The successful run made one create/authenticate/refresh/revoke sequence, with exact identity-tagged cleanup. Passwords, keys and tokens were not printed or included here.

Primary contracts: [password authentication](https://workos.com/docs/reference/authkit/authentication/password), [refresh](https://workos.com/docs/reference/authkit/authentication), [session revocation](https://workos.com/docs/reference/authkit/session).
