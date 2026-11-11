Upgrade candidate accessibility preflight

Root file-hash verification does not prove that the service user can read a
candidate. main now runs verify_service_access before activation/readiness.
It changes directory, reads every manifest member, checks traversal/listing,
and imports the exact candidate vipi.api/config as the existing vipi identity.
PYTHONDONTWRITEBYTECODE and -B prevent changes to package contents. It does not
instantiate Settings, a database or provider, call main/activate on the tested
server, or alter service state. Timeout is60seconds; errors fail closed without
echoing environment/import exception contents.

verify_release remains unchanged and pure for offline packaging callers.
Local permission fixtures use existing nobody on an owned disk-backed tree;
root hashes still pass while0700/0600permissions are rejected. Actual vipi-user
preflight passed on retained b144 runtime without restart. The new upgrade
helper is not deployed by this qualification; it is source for the next package.
