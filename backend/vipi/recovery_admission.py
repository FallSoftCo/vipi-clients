"""Database-local restore quarantine; deliberately no release operation.

Marker presence (even empty/malformed) denies ordinary connections. Offline
recovery is an explicit library capability, never an environment switch.
"""

from sqlalchemy import event, text

MARKER = "vipi_restore_hold"


class RecoveryHoldError(RuntimeError):
    def __init__(self):
        super().__init__("restored_database_recovery_hold")


def install_admission(engine):
    dialect = engine.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise ValueError("unsupported recovery admission dialect")

    @event.listens_for(engine.sync_engine, "checkout")
    def check(connection, record, proxy):
        cursor = connection.cursor()
        try:
            if dialect == "sqlite":
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='vipi_restore_hold'"
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='vipi_restore_hold'"
                )
            held = cursor.fetchone() is not None
        finally:
            cursor.close()
            # Admission runs before a connection is handed to its borrower.
            connection.rollback()
        if held:
            raise RecoveryHoldError()


def marker_name(db):
    dialect = db.engine.dialect.name
    if dialect == "postgresql":
        return "public.vipi_restore_hold"
    if dialect == "sqlite":
        return "vipi_restore_hold"
    raise ValueError("unsupported recovery marker dialect")


async def mark_restore(db, *, snapshot_sha256, snapshot_at, restore_id):
    """Commit HOLD before applying any restored contents/reconciliation.

    Only an offline database handle may install a marker. A retry cannot rebind
    a marker to another restore. Table existence itself is the fail-closed gate.
    """
    if not db.offline_recovery:
        raise ValueError("offline recovery handle required")
    import re
    from uuid import UUID

    if (
        not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256)
        or str(UUID(restore_id)) != restore_id
    ):
        raise ValueError("invalid restore binding")
    if snapshot_at.tzinfo is None:
        raise ValueError("aware snapshot time required")
    table = marker_name(db)
    async with db.engine.begin() as c:
        await c.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {table} "
                "(singleton INTEGER PRIMARY KEY, snapshot_sha256 VARCHAR(64) NOT NULL, "
                "snapshot_at VARCHAR(64) NOT NULL, restore_id VARCHAR(36) NOT NULL, state VARCHAR(16) NOT NULL)"
            )
        )
        rows = (await c.execute(text(f"SELECT * FROM {table}"))).mappings().all()
        expected = dict(
            singleton=1,
            snapshot_sha256=snapshot_sha256,
            snapshot_at=snapshot_at.isoformat(),
            restore_id=restore_id,
            state="HOLD",
        )
        if rows:
            if len(rows) != 1 or dict(rows[0]) != expected:
                raise ValueError("restore marker binding conflict")
        else:
            await c.execute(
                text(
                    f"INSERT INTO {table} "
                    "(singleton,snapshot_sha256,snapshot_at,restore_id,state) "
                    "VALUES (:singleton,:snapshot_sha256,:snapshot_at,:restore_id,:state)"
                ),
                expected,
            )
    return expected


async def require_restore_binding(db, snapshot_sha256):
    if not db.offline_recovery:
        raise ValueError("offline recovery handle required")
    table = marker_name(db)
    async with db.engine.connect() as c:
        rows = (await c.execute(text(f"SELECT * FROM {table}"))).mappings().all()
    if (
        len(rows) != 1
        or rows[0]["state"] != "HOLD"
        or rows[0]["snapshot_sha256"] != snapshot_sha256
    ):
        raise ValueError("restore marker binding conflict")
    return dict(rows[0])
