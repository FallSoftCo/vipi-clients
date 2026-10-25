#!/usr/bin/env python3
"""First installation only. A verified, prebuilt release must already exist.
No shared service restart, package installation, firewall or nginx mutation.
Pass the staging WorkOS subject allowlist as a JSON array on stdin.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import socket
import subprocess
import sys

assert socket.gethostname() == "ubuntu-16gb-ash-1" and os.geteuid() == 0
revision = sys.argv[1]
assert re.fullmatch(r"[0-9a-f]{40}", revision)
release = Path("/opt/vipi/releases") / revision
manifest = json.loads((release / "manifest.json").read_text())
assert manifest["revision"] == revision
for name, digest in manifest["files"].items():
    assert not Path(name).is_absolute() and ".." not in Path(name).parts
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == digest, name
subjects = json.load(sys.stdin)
assert isinstance(subjects, list) and 1 <= len(subjects) <= 20
assert all(isinstance(s, str) and re.fullmatch(r"user_[A-Za-z0-9]+", s) for s in subjects)
assert not Path("/opt/vipi/current").exists() and not Path("/etc/vipi/service.env").exists()
assert subprocess.run(["getent", "passwd", "vipi"], stdout=subprocess.DEVNULL).returncode != 0
def sql(statement, database="postgres"):
    return subprocess.check_output(["runuser", "-u", "postgres", "--", "psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", "-d", database, "-c", statement], text=True).strip()
assert not sql("SELECT rolname FROM pg_roles WHERE rolname IN ('vipi','vipi_owner')")
assert not sql("SELECT datname FROM pg_database WHERE datname='vipi'")
with socket.socket() as probe: probe.bind(("127.0.0.1", 48943))

record = Path("/opt/vipi/provisioning-001.json")
receipt = {"owner": "01a16e0d-ac69-7dd0-872a-8cf087160515", "release": revision,
    "host": socket.gethostname(), "staging_subject_count": len(subjects), "steps": []}
def done(step):
    receipt["steps"].append(step); record.write_text(json.dumps(receipt, indent=2)); record.chmod(0o600)
done("manifest_and_empty_namespace_verified")
subprocess.run(["useradd", "--system", "--home-dir", "/var/lib/vipi", "--create-home", "--shell", "/usr/sbin/nologin", "vipi"], check=True)
done("unix_account_created")
sql("CREATE ROLE vipi_owner NOLOGIN")
sql("CREATE ROLE vipi LOGIN")
sql("CREATE DATABASE vipi OWNER vipi_owner")
sql("REVOKE ALL ON DATABASE vipi FROM PUBLIC; GRANT CONNECT ON DATABASE vipi TO vipi")
done("isolated_database_roles_created")
env = os.environ.copy()
env.update(PYTHONPATH=str(release / "deps"), PYTHONDONTWRITEBYTECODE="1",
    VIPI_DATABASE_URL="postgresql+asyncpg://postgres@/vipi?host=/var/run/postgresql", VIPI_MIGRATION_ROLE="vipi_owner")
subprocess.run(["runuser", "-u", "postgres", "--", "/usr/bin/python3", "-m", "alembic", "-c", str(release / "alembic.ini"), "upgrade", "head"], env=env, cwd=release, check=True)
sql("REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO vipi; "
    "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO vipi; "
    "REVOKE INSERT,UPDATE,DELETE ON alembic_version FROM vipi; "
    "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO vipi; "
    "ALTER DEFAULT PRIVILEGES FOR ROLE vipi_owner IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO vipi; "
    "ALTER DEFAULT PRIVILEGES FOR ROLE vipi_owner IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO vipi", "vipi")
assert sql("SELECT has_schema_privilege('vipi','public','CREATE'),pg_has_role('vipi','vipi_owner','MEMBER')", "vipi") == "f|f"
done("schema_migrated_runtime_has_no_ddl_or_owner_membership")
config = Path("/etc/vipi"); config.mkdir(mode=0o750)
user = pwd.getpwnam("vipi"); os.chown(config, 0, user.pw_gid)
values = {"VIPI_DATABASE_URL": "postgresql+asyncpg://vipi@/vipi?host=/var/run/postgresql",
    "VIPI_WORKOS_CLIENT_ID": "client_01M5QPQSVXQDEJGQ1CYZ75MSGS", "VIPI_WORKOS_ISSUER": "https://api.workos.com",
    "VIPI_SERVICE_SECRET": secrets.token_urlsafe(32), "VIPI_ENVIRONMENT": "staging",
    "VIPI_ALLOWED_SUBJECTS": "'" + json.dumps(subjects, separators=(",", ":")) + "'"}
environment = config / "service.env"
environment.write_text("\n".join(key + "=" + value for key, value in values.items()) + "\n")
os.chown(environment, 0, user.pw_gid); environment.chmod(0o640)
Path("/opt/vipi/current").symlink_to(release)
done("private_configuration_and_release_link_created")
for name in ("vipi-api.service", "vipi-expiry.service", "vipi-expiry.timer"):
    source = release / "ops" / name; target = Path("/etc/systemd/system") / name
    assert not target.exists(); target.write_bytes(source.read_bytes()); target.chmod(0o644)
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(["systemctl", "enable", "--now", "vipi-api.service", "vipi-expiry.timer"], check=True)
done("owned_services_enabled")
print(json.dumps({"receipt": str(record), "release": revision, "staging_subject_count": len(subjects)}))
