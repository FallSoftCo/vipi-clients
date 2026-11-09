# Retained cached-target inventory: preparation only

**Next fixed cohort:** retain all200 Taskmaster English conversation turns and use their already captured EN→ES targets. There are186 successful full targets, not200; the14 `INVALID_LANGUAGE` cases must remain explicit null outcomes, with no fresh translation or outcome-based replacement. This gives a broader conversational alignment test while changing neither source sampling nor the target provider. It tests iOS dictionary alignment over retained Android ML Kit output, **not** new Apple translation quality.

| Existing raw capture | Pair | Source rows | Exact full targets | Capture bytes |
|---|---|---:|---:|---:|
|taskmaster-ceiling-001.json|EN→ES and EN→SW|200 each|186 each|1,460,283 total|
|coverage-ceiling-001.json|EN→ES and EN→SW SMS|200 each|191 each|2,023,214 total|
|conversational-routing-001.json|EN→SW BST|80|77|646,046|
|directional-ceiling-001.json|EN→JA; ES→EN|200 each|186;183|2,143,122 total|

All four raw captures are complete and their recorded input SHA equals the exact retained source protocol SHA. Provider is Google ML Kit translate17.0.3 on device. Missing full targets above are `INVALID_LANGUAGE` outcomes. No differing full targets across the retained density captures were found; density repeats are not independent source evidence. Full target text is separate from selected spans and remains available even where no mixed span was selected.

Taskmaster contains200 distinct conversation IDs but only185 unique NFC/casefold/whitespace-normalized source strings (short turns repeat). It spans seven domains; original prior-dialogue metadata is retained for assessment, not invented model input. EN→JA reuses these185 normalized Taskmaster sources and is not an independent English cohort. The SMS set has200 unique sources; BST has80 unique sources from80 test conversations. Each collection has zero exact normalized source overlap with the eight current diagnostic cases; Taskmaster, SMS and BST also have zero mutual normalized overlap. **All have prior project exposure/reviews** and are not pristine held-out population samples. No label-based reselection is proposed. Taskmaster attribution/license/source hashes and BST/SMS sampling provenance stay in their original frozen protocols; inventory JSON binds those files rather than treating public research messages as private customer chat.

## Existing native readiness and protections

A read-only current simulator cache listing found:

- English dictionary207,884,288B, Spanish364,613,632B, Swahili14,819,328B.
- EN→ES witness59,809,792B and EN→SW witness1,429,504B.

Names include the existing content hashes; this was a size/path inventory, **not a fresh full asset rehash**. The completed eight-case EN→ES run verifies the current native reader route. Swahili has retained targets and dictionary/witness assets, so a later no-provider replay is technically plausible; this is not Swahili alignment/meaning qualification. Apple Translation's unsupported Swahili route does not invalidate replay of previously captured ML Kit targets. Do not call it fresh Apple or offline-provider translation.

EN→JA cached targets exist, but Japanese dictionary/reading/witness files were absent from the current simulator lexical cache listing. A broader non-Roman replay therefore needs exact retained asset staging/readings qualification before it is called ready. No download or model acquisition is proposed here. The older34 authored/contrast capture (119,307B) has27 EN→ES plus seven single-case other directions, useful as exposed controls rather than conversational coverage.

The raw Android records retain native source geometry (199/200 Taskmaster,200/200 SMS,80/80 BST; target geometry inside provider call records), but no explicit per-case supplied-protection field. A future replay must retain original text and input failures, then use the existing current native recognition APIs for all named/supplied/enclosing/identifier protections. Do not silently interpret a missing stored mask array as permission or copy token indices across platforms. Full primary/competing inventories and every unlinked form must remain, as in the eight-case probe. Recompute geometry/recognition on the authorized native route without making translation calls, and freeze these bindings before comparing outputs.

## Scope decision

Prefer the complete fixed200-row Taskmaster EN→ES capture first, with186 cached targets and14 null controls. Keep SMS and BST as separate domains/providers/previous-exposure strata; do not merge them to inflate independent sample counts. The existing eight cases remain development controls. Report complete mixed-message depth, useful-content gains/losses and semantic problems for changed outputs—not just more dictionary matches. EN→SW and non-Roman extensions require their own explicit readiness and interpretation; Spanish results do not qualify them.

`cached-cohort-inventory.json` and `cached-native-assets-inventory.json` are retained privately with file sizes, hashes, exact source pins, overlap counts and limitations. This was read-only inventory. No expansion alignment, translation call, build, threshold search or app activation occurred after the eight-case closure.
