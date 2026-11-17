# Vipi — draft information for French cryptology declaration

Working draft, 17 November 2026. Not submitted; no ANSSI receipt or exemption is claimed. The legal classification and the person authorized to sign must be confirmed before submission.

The official [ANSSI declaration procedure](https://demarche.numerique.gouv.fr/commencer/declaration-relative-a-un-moyen-de-cryptologie) requires a portal account and lists a company presentation, a commercial-register extract less than three months old (or the foreign equivalent), a commercial brochure, a technical brochure and user/admin guides if available. Confirm the current form and any applicable exception directly with ANSSI. Apple lists a French declaration for distribution in France in its [encryption documentation table](https://developer.apple.com/help/app-store-connect/reference/app-information/export-compliance-documentation-for-encryption).

## Known product facts

- Product: Vipi, consumer messaging application by Fallible Software, Co. (App Store developer display: Fallible Software, Co.; Apple app ID 6832624092).
- Purpose: friends exchange messages; selected words in messages can switch to a language the reader is learning. Messaging security is intended to protect messages in transit and storage.
- Fixed-function client cryptography: published Signal protocols through pinned libsignal 0.105.0; Kyber-1024 round 3 KEM; AES-GCM local storage; encrypted user-directed history backup using AES-256-GCM and PBKDF2-HMAC-SHA256, 600,000 iterations. Exact source and further classification context: [EXPORT_ASSESSMENT.md](EXPORT_ASSESSMENT.md).
- Do not represent round 3 Kyber as FIPS 203 ML-KEM or claim a FIPS certification. No proprietary or unpublished algorithm is asserted merely because the app uses external libraries.
- Available technical starting materials: export assessment, source and dependency lockfiles, and `qa/backup/format-v1.json`. Prepare an accurate submission-specific technical brochure from the exact release source and dependencies; review it before filing.

## Information and attachments to obtain or prepare

1. Confirm the company's exact legal name, registered address, jurisdiction, legal representative, contact details and authority to file from primary corporate records.
2. Obtain a current foreign equivalent of the register extract dated within the procedure's stated three-month window. None identified in the scoped release records reviewed so far.
3. Prepare a company presentation and commercial product brochure from approved product copy, with accurate availability and pricing at filing time.
4. Prepare and review a technical brochure, user guide and any applicable administrator guide. Verify cryptographic roles, versions, key management, source availability and whether additional attachments are requested by the actual form.
5. Complete the official portal process and retain the real receipt and any correspondence; upload only the document Apple requests. Do not fabricate registration numbers, signatures, classifications, approval or filing receipts.

Worldwide distribution, including France, was requested; Apple build association and release remain subject to truthful compliance and remaining launch qualification. Separate China mainland requirements are displayed in App Store Connect and must be reconciled independently.

## Separate China mainland inventory

[Apple's current app-compliance reference](https://developer.apple.com/help/app-store-connect/reference/app-information/app-and-compliance-information/) states that apps offering AI chatbots must declare those services and provide approved LLM or algorithm filing information, together with a third-party technology authorization or usage agreement where applicable. It also lists proof and a copy of a completed security assessment for end-to-end encrypted instant messaging. ICP filing information may also apply. Vipi has vBot and encrypted messaging; determine the actual applicability and required documents for the intended offering. No China filing, provider agreement for this purpose or security-assessment receipt has been established by this inventory.
