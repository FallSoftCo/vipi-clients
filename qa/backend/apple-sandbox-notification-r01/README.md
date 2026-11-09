# Actual Apple Sandbox TEST notification

On November 9, 2026, Apple delivered one signed V2 TEST notification to Vipi’s
restricted staging callback. The official SDK verified it; the database retained
the matching event ID/fingerprint, Apple reported SUCCESS, and entitlement counts
remained empty. Invalid signed payloads return 400. The configured sandbox URL
was verified after reloading App Store Connect; the production URL remains unset.

The service kept the same code/schema and restricted subject allowlist. Only its
Apple Sandbox verifier configuration changed. The scoped API restart took 4.57
seconds; shared nginx/PostgreSQL processes stayed unchanged. Earlier preparation
failures occurred before activation or before any test request and are retained
privately; the successful Apple request was made once as the service identity.

`receipt.json` records the evidence and private receipt hashes. It contains no
private key, test token or signed payload. Real purchases, renewal, refund,
revocation, restore and production billing remain unqualified. See Apple’s
[TEST endpoint](https://developer.apple.com/documentation/appstoreserverapi/request-a-test-notification).
