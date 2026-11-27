#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path("/Users/Apple/Development/vipi")
DEVICE = "46CB569D-EA59-40E3-82CC-F4A0F36EDB87"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def container():
    return Path(
        subprocess.check_output(
            [
                "xcrun",
                "simctl",
                "get_app_container",
                DEVICE,
                "co.fallsoft.vipi",
                "data",
            ],
            stdin=subprocess.DEVNULL,
        )
        .decode()
        .strip()
    )


cases = ROOT / "artifacts/bundled-development-004/combined-cases.json"
assert sha(cases) == "31749d51dce948d425ceb3e6d381587db35d66b8c1d4f5af5e621cc3b263b454"
assert (
    sha(ROOT / "data/lexical/catalog.json")
    == "6b8040ae0eacb82dded24d9cf948649551195165d3d1c12a085e17e02e847300"
)
report = ROOT / "artifacts/bundled-conversations-simulator-014.json"
result = ROOT / "artifacts/present-verb-ios-build-001.xcresult"
assert not report.exists() and not result.exists()
docs = container() / "Documents"
(docs / "bundled-conversation-cases.json").write_bytes(cases.read_bytes())
(docs / "bundled-conversation-run.txt").write_text("014 " + sha(cases) + "\n")
with (ROOT / "artifacts/present-verb-ios-build-001.log").open("x") as log:
    subprocess.run(
        [
            "xcodebuild",
            "-workspace",
            "Vipi.xcworkspace",
            "-scheme",
            "VipiSimulator",
            "-configuration",
            "Simulator",
            "-sdk",
            "iphonesimulator",
            "-destination",
            "platform=iOS Simulator,id=" + DEVICE + ",arch=arm64",
            "-derivedDataPath",
            "../build/ios-simulator",
            "-parallel-testing-enabled",
            "NO",
            "-collect-test-diagnostics",
            "never",
            "-only-testing:VipiCryptoTests/BundledConversationReplayTests",
            "-resultBundlePath",
            str(result),
            "ARCHS=arm64",
            "EXCLUDED_ARCHS=",
            "CODE_SIGNING_ALLOWED=YES",
            "CODE_SIGN_IDENTITY=-",
            "test",
        ],
        cwd=ROOT / "ios",
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
report.write_bytes(
    (container() / "Documents/bundled-conversations-014.json").read_bytes()
)
v = json.loads(report.read_text())
assert (
    v["complete"]
    and not v["failures"]
    and v["run"] == "014"
    and len(v["outcomes"]) == 602
)
assert v["cases_sha256"] == sha(cases) and v["bundled_catalog_sha256"] == sha(
    ROOT / "data/lexical/catalog.json"
)
print(json.dumps(dict(complete=True, report_sha256=sha(report), cases=602)), flush=True)
