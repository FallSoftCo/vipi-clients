# Encryption export assessment

Reviewed November 10, 2026. This records the technical basis for the Vipi client
release; it is not a government classification, a filing receipt or a claim that
the stores have accepted the application.

The fixed-function consumer clients use libsignal 0.105.0 and its published
protocols. Android requests Kyber-1024 prekeys; Apple uses corresponding KEM
prekeys. Local storage uses AES-GCM. User-directed history backups use
AES-256-GCM and PBKDF2-HMAC-SHA256 with 600,000 iterations. The backup format is
documented in `qa/backup/format-v1.json`. There is no user-selectable cipher,
cryptographic toolkit, network-infrastructure product, forensic capability or
government-specific customization in these clients. Post-quantum key
encapsulation is distinct from quantum key distribution.

The pinned libsignal 0.105.0 source uses `libcrux_ml_kem::kyber1024`
from libcrux-ml-kem 0.0.10 for its Kyber-1024 KEM. The library describes
this as [Kyber 1024, NIST PQC Round 3](https://docs.rs/libcrux-ml-kem/0.0.10/libcrux_ml_kem/),
which is distinct from the final FIPS 203 ML-KEM-1024 variant. Do not describe
it as an implementation of, or certified to, FIPS 203 merely because the
crate name includes ML-KEM. The [Kyber specification](https://pq-crystals.org/kyber/)
and [Signal PQXDH protocol](https://signal.org/docs/specifications/pqxdh/)
are published. Publication matters: Apple and BIS describe non-standard
cryptography in terms of proprietary or unpublished functionality that has
not been adopted by a recognized standards body and has not otherwise been
published; lack of final FIPS standardization alone does not establish that
classification. See [Apple’s export overview](https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance/)
and [BIS guidance](https://www.bis.gov/learn-support/encryption-controls/license-exception-enc-740.17-b-3).

These facts support the ordinary consumer-software self-classification route
under [740.17(b)(1)](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-740/section-740.17).
For mass-market treatment, retain the final retail facts: public store
distribution, published features and prices, installation by the customer, and
fixed installed cryptographic functionality. The relevant criteria are in
[Note 3](https://www.bis.gov/media/documents/resources-note-3-c5p2.pdf).
The restricted test service is not already a public retail launch. Reconcile
the final dependency inventory and distribution choices before completing
the store declarations; no prior CCATS or 30-day wait has been identified for
this client configuration.

The earlier blanket source-notification and annual-report assumptions are
superseded. Current [742.15(b)(2)](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-742/section-742.15)
limits the public-source notification requirement to non-standard cryptography.
The ordinary mass-market application also does not automatically fall into the
remaining annual reporting categories in 740.17(e)(3). The
[BIS 2021 change table](https://www.bis.gov/media/documents/table-changes-enc-wa2019-rule-final-version.pdf)
explains both changes. Broad introductory guidance must not replace those
specific provisions.

Public source preparation and signed-binary correspondence are different steps.
Qualifying source publication need not wait for a signed release, but a private
archive is not publicly available source. Preserve the source, dependency and
format documentation and bind the published archive to the eventual binaries.
No government email, filing or notification has been sent for Vipi by this work.

Country-specific requirements remain separate. Apple's
[encryption documentation table](https://developer.apple.com/help/app-store-connect/reference/app-information/export-compliance-documentation-for-encryption/)
specifies a French declaration for applicable external standard cryptography
when distributing in France. Do not answer that Vipi uses only OS encryption:
libsignal is an external dependency. Final storefront choices and declarations
have not been saved.

This export assessment does not establish software-license compatibility.
Google ML Kit's exact linked terms remain a separate dependency review; neither
Signal's App Store availability nor its Firebase usage grants Vipi a new
permission for ML Kit.
