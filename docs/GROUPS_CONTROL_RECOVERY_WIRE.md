# Disabled upgrade: CONTROL routing recovery checkpoint

At `befc3fc9`, CONTROL fanout is exactly the current eligible non-sender routes.
Missing/inactive devices, deleted/suspended users and peers blocked with the
**authenticated sender** are omitted. Both block directions count. A snapshot
returned to that actor gives these members `device_id: null`; their people and
roles remain in the complete roster proposal. Another actor can have a different
routing view. This is routing availability, never authenticated membership.

DATA is unchanged: every current member must be active/unrestricted, have exactly
one active device and have no block between any roster pair. An unavailable
member is never silently dropped from ordinary message fanout. Multiple active
devices fail closed for CONTROL and DATA, including an otherwise ineligible user.
An optional pending invitee still needs valid invitation/admin authority, a
usable account/device, and no block with existing members. It is not omitted.

Membership mutation and its immutable control still share one transaction and
original saved admission. Removal of the last unavailable other member may have
an empty control fanout; the admitted control and exact intended mutation remain
recorded. It does not manufacture delivery/read to that unavailable person.
Known original admission/cancellation fingerprints and outcomes are unchanged.

The native candidate at clients `255b4f08` omits nil routes only for CONTROL while
validating the whole approved previous roster and intentional transition. DATA
stays strict. A joining member must have a usable route before ADD/bootstrap.
Native prepare-peer work uses only those proposed CONTROL routes; it must not
infer a new identity or approve a server-proposed roster. An omitted member's
old local history is preserved. An unavailable member returning without its
authenticated control chain still needs secure recovery; this transport change
does not silently authorize a newer server roster.

Qualification is explicitly split:

* PostgreSQL `befc3fc9`:56 passed,0failed/skipped,69.32s, including9 new routing
  cases and existing admission/cancellation/lock regressions. Original first
  SQLite run48PASS/1FAIL was a bad test-only Block.created_at field; corrected
  full PostgreSQL run passed. Cluster stopped, disposable database dropped,
 0test schemas/other clients. Receipt in the private investigation:
 `groups-durable-recovery-r01/control-eligible-pg-r01/`.
* Android candidate `447c6438`:build passed;4 native tests passed,0skips,2.397s.
  Real Signal approvals, unavailable-device removal, strict DATA, reachable ADD,
  and exact recovery-descriptor/reply binding were exercised. Session compiles.
* Apple candidate `6b4eae62`:build including Session passed;7 native core tests
  passed,0skips. Real Signal ADD/bootstrap, removal of an ineligible route, fresh
  remaining-recipient DATA and existing hold/rollback/membership checks passed.
* Earlier separate three-user Android/iOS API/Signal/storage proof passed8/8
  original stages at protocol `ff1ee813`, Android `08c87a15`, Apple `c1687cde`.
  Three fresh local identities, normal signed authentication/PostgreSQL HTTP,
  offline vault catch-up, exact four message IDs and0duplicates;17envelopes all
  delivered. That proves the original all-eligible path, not the new repair UI.

These are component/native and normal-API qualifications, not a complete group
customer journey. New-route end-to-end UI/recovery, durable native cancellation
and saved-outcome reconciliation, returning-member control-history recovery,
remote per-member read, private CAS mute/push,16-person integration, localization
and alias-migration reconciliation remain gates. Android's typed recovery API
is qualified only for original-device/body capture and reply binding; existing
Session mutation journals do not yet use it. Apple typed recovery parity is
pending. No implicit discard, new request ID, ratchet rollback or production
activation follows. Groups remains OFF and independent of launch.
