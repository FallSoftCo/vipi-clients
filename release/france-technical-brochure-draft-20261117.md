# Vipi — draft cryptology technical description

Working attachment for review; not a government classification, approval or filing. Verify every version and build correspondence against the final release before use.

Vipi is a fixed-function consumer messaging client, not a general-purpose cryptography toolkit. The clients use the published Signal protocols through libsignal 0.105.0 for encrypted friend messaging. The pinned library uses Kyber-1024 from the NIST post-quantum competition round 3 for key encapsulation; this is distinct from final FIPS 203 ML-KEM-1024 and no FIPS certification is asserted. Local storage uses AES-GCM. User-directed encrypted history export uses AES-256-GCM with PBKDF2-HMAC-SHA256 and 600,000 iterations.

The user cannot choose a cipher or modify cryptographic parameters through the client UI. The product includes no quantum key distribution. Messaging identity, server functions, recovery and backup limitations must be described precisely in the final technical and user guides. The backup format is documented in `qa/backup/format-v1.json`.

Source and classification evidence: [EXPORT_ASSESSMENT.md](EXPORT_ASSESSMENT.md), pinned dependency and source manifests, [Signal PQXDH](https://signal.org/docs/specifications/pqxdh/) and [Kyber specification](https://pq-crystals.org/kyber/). Inventory actual target platforms, cryptographic primitives, key lifecycle, implementation source and build correspondence from the final artifact; confirm any French portal-specific questions and attachments with ANSSI. No filing number, authorization, security evaluation or official receipt is claimed.
