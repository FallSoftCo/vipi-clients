# Superseded partial database

After the completed evidence and source checkpoint were independently verified,
root retired only `join-r01/evidence.sqlite` on November 9 at 09:00:28 UTC.
The 94,363,648-byte failed prefix had SHA256
`3a44b59ddce5b834384f1dc29e4b0c6b2d9e279b5dd6d4fc7c5490ccb56a3261`.

Immediately before removal, root rehashed both databases, verified zero open
readers, and again compared every prefix object and relation against the complete
database. No object was missing or changed; no relation was missing. The complete
database remains at `join-r02/evidence.sqlite`, SHA256
`03415f4547ed645a9dc5e9283ab4bfb77621e8ebb801f46f608a75b6053b01e3`.
Failure source, protocol and receipts remain available.

The original completion receipt records the state before this retirement and is
unchanged. The later receipt is
`superseded-database-retirement-r01.json` in the private investigation directory
and `join-r01/` in the production evidence directory. Source was already retained
at private checkpoint `refs/heads/checkpoints/production-20261109-r15`.
