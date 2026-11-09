The frozen context evidence now has a deterministic SQLite runtime artifact. The
measurement and export stages each ran once on the consolidated production host,
with no new corpus inference or customer activation.

The pack is **4,890,624 bytes**, SHA256
`cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4`.
It retains all 1,157 rules, 453 original heads, 2,091 rule/head support edges,
326 dictionary forms, 651 terms and 5,328 exact supported link tuples. All 23
winning rules without admitted heads survive: a missing output cannot expose a
shorter match. Known-family, source-role and function-classification tables remain
separate from actual user knowledge. The 2,610,661-byte audit manifest stays
outside the runtime pack.

The exporter reproduced identical bytes from two builds on SQLite 3.45.1 and
checked every decoded row, integrity and foreign keys. Root separately compared
all rule values, admitted heads, original readings, link membership, dictionary
metadata and audit-edge bindings with the frozen inputs. Export took 4.96 seconds
with a 286,089,216-byte parent VmHWM; these are authoring costs, not mobile lookup
latency or RAM. Both stages stayed within their frozen limits.

This is a disabled English→Spanish research add-on. It grants no display
permissions, includes no ordinary baseline producer, and establishes no new
linguistic coverage. Dictionary recognition, source protections, exact native
geometry, role evidence, target/forms, known families and selection still require
native integration. Unicode normalization/tokenization must be qualified rather
than replaced with lowercase-only word ngrams. The frozen preparation contract
and protocol retain their pre-execution wording; this result and the receipts
record the later explicitly authorized execution.
