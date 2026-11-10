# Corrected data candidate

Private r02 now contains SW 237 entries (222 active +15) and JA 197 (189 active +8). All active entries and original 70 fixtures remain unchanged. There are no runtime edits or native executions.

Removed unguarded Japanese free time/spare time because the observed parking-price and spare-[time machine] cases do not mean leisure. Removed the new SW police officer, this morning, boarding school, common cold, sweet potato and JA country music entries pending scoped source-context support. The existing ordinary_noun_context guard does **not** fix their actual title controls: each is sentence-initial and followed by “is,” an explicitly permitted copula. Applying that guard would merely hide an unresolved error behind a guard name.

Retained Japanese high school with the existing ordinary_noun_context guard: the ordinary source has “in high school,” which passes; “High School Musical…” has neither an allowed left context nor a right copula and is withheld. This is static source-branch assessment, not native qualification. It does not establish general name recognition: other high-school titles or “High School is…” may still pass. Root's native capture must verify exact behavior, masks and changes against both baseline and r01.

Other new entries, target faces, readings, ranks and concept groups are unchanged. The high-school proof and record hash are explicitly amended; removed records remain preserved in immutable r01. `correction.json` retains exact removals, guard assessments with complete fixture sources, and parent/review hashes. `candidate-r02-validation.json` checks all 23 new proof bindings and fixture byte parity.

No negative fixture is deleted or softened. Some attested remaining entries were not selected in r01 and have no new-output coverage or semantic acceptance claim. Title-related judgments remain an explicitly disclosed exact-name presentation policy, separate from the two unambiguous leisure/constituent errors. Neither this correction nor dictionary attestation constitutes a broad accuracy guarantee.
