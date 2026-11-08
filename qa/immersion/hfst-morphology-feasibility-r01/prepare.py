"""Isolated, checksum-pinned research tools; never installs system packages."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
packages = ["hfst", "libhfst55", "libfoma0t64", "libfst22", "lexd", "liblttoolbox3"]
records = []
for package in packages:
    text = subprocess.check_output(["apt-cache", "show", package], text=True).split("\n\n")[0]
    fields = dict(line.split(": ", 1) for line in text.splitlines() if ": " in line and not line.startswith(" "))
    records.append({k: fields[k] for k in ["Package", "Version", "Filename", "SHA256", "Size", "Installed-Size", "Depends"]})
budget = 256 * 1024 * 1024
free = shutil.disk_usage(ROOT).free
assert free > budget + 2 * 1024**3, free
plan = {"schema": "vipi.hfst-feasibility-plan.r01", "production": False,
        "created_utc": datetime.now(timezone.utc).isoformat(), "free_before": free,
        "additional_disk_cap_bytes": budget, "per_process_address_space_cap_bytes": 1024**3,
        "per_process_cpu_seconds": 120, "per_process_wall_seconds": 180,
        "purpose": "Qualify isolated HFST/lexd morphology on pinned retained Swahili source. No native integration or translation-coverage inference.",
        "package_mutation": "Extract .deb files into this owned directory only; no apt install, system PATH or service change.",
        "packages": records}
(ROOT / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
download = ROOT / "packages"
prefix = ROOT / "prefix"
download.mkdir(exist_ok=True)
prefix.mkdir(exist_ok=True)
for rec in records:
    path = download / Path(rec["Filename"]).name
    if not path.exists():
        request = urllib.request.Request("https://archive.ubuntu.com/ubuntu/" + rec["Filename"], headers={"User-Agent": "Vipi-qualified-research/1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            blob = response.read(int(rec["Size"]) + 1)
        assert len(blob) == int(rec["Size"])
        assert hashlib.sha256(blob).hexdigest() == rec["SHA256"]
        path.write_bytes(blob)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == rec["SHA256"]
    subprocess.run(["dpkg-deb", "-x", str(path), str(prefix)], check=True, timeout=20)
env = dict(os.environ, LD_LIBRARY_PATH=str(prefix / "usr/lib/x86_64-linux-gnu"))
checks = []
for tool in ["hfst-lookup", "hfst-optimized-lookup", "hfst-txt2fst", "hfst-invert", "hfst-fst2fst", "hfst-minimise", "lexd"]:
    executable = prefix / "usr/bin" / tool
    version = subprocess.run([str(executable), "--version"], env=env, capture_output=True, text=True, timeout=10)
    checks.append({"tool": tool, "returncode": version.returncode, "stdout": version.stdout, "stderr": version.stderr,
                   "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()})
    assert version.returncode == 0, checks[-1]
receipt = {"schema": "vipi.hfst-isolated-tools.r01", "checks": checks,
           "regular_file_bytes": sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file() and not p.is_symlink()),
           "system_packages_installed": False}
(ROOT / "tool-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({"versions": [{"tool": c["tool"], "output": c["stdout"].splitlines()[0]} for c in checks], "bytes": receipt["regular_file_bytes"]}))
