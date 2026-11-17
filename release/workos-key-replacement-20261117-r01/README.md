The exposed Vipi WorkOS key was replaced once and the original expired immediately after the live replacement passed verification. The old credential now returns HTTP 401; the new credential returns HTTP 200 for the existing owned QA user. The API passed readiness, and push, nginx and PostgreSQL stayed running. No app identity migration, user change, message, purchase or store submission occurred.

The production settings candidate was rebased separately as r03. The old environment and r02 candidate contain the revoked key and must not be restored.
