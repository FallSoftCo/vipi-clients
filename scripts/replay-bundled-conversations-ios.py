#!/usr/bin/env python3
"""Replay captured sentence pairs through the native iOS reader on the owned simulator."""
import argparse, hashlib, json, platform, shutil, subprocess
from pathlib import Path
ROOT = Path("/Users/Apple/Development/vipi")
DEVICE = "46CB569D-EA59-40E3-82CC-F4A0F36EDB87"
def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
def command(*args):
    return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, check=True).stdout
def container():
    return Path(command("xcrun", "simctl", "get_app_container", DEVICE, "co.fallsoft.vipi", "data").decode().strip())
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--expected-catalog", required=True)
    args = parser.parse_args()
    assert platform.system() == "Darwin" and args.run.isdigit()
    cases = args.cases.resolve()
    inputs = json.loads(cases.read_text())
    count = len(inputs) if isinstance(inputs, list) else len(inputs["cases"])
    assert count > 0
    assert sha(ROOT / "data/lexical/catalog.json") == args.expected_catalog
    result = ROOT / ("artifacts/bundled-conversations-simulator-" + args.run + ".xcresult")
    report = result.with_suffix(".json")
    log = result.with_suffix(".log")
    assert not result.exists() and not report.exists() and not log.exists()
    documents = container() / "Documents"
    documents.mkdir(exist_ok=True)
    shutil.copyfile(cases, documents / "bundled-conversation-cases.json")
    (documents / "bundled-conversation-run.txt").write_text(args.run + " " + sha(cases) + "\n")
    with log.open("x") as stream:
        subprocess.run(["xcodebuild", "-workspace", "Vipi.xcworkspace", "-scheme", "VipiSimulator",
            "-configuration", "Simulator", "-sdk", "iphonesimulator", "-destination",
            "platform=iOS Simulator,id=" + DEVICE + ",arch=arm64", "-derivedDataPath", "../build/ios-simulator",
            "-parallel-testing-enabled", "NO", "-collect-test-diagnostics", "never",
            "-only-testing:VipiCryptoTests/BundledConversationReplayTests", "-resultBundlePath", str(result),
            "ARCHS=arm64", "EXCLUDED_ARCHS=", "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-", "test"],
            cwd=ROOT / "ios", stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, check=True)
    raw = (container() / ("Documents/bundled-conversations-" + args.run + ".json")).read_bytes()
    with report.open("xb") as stream:
        stream.write(raw)
    value = json.loads(raw)
    assert value["complete"] and not value["failures"] and len(value["outcomes"]) == count
    assert value["cases_sha256"] == sha(cases) and value["bundled_catalog_sha256"] == args.expected_catalog
    print(json.dumps(dict(complete=True, report_sha256=sha(report), cases=count,
        catalog_sha256=args.expected_catalog, physical_device_verified=False, translation_reused=True)), flush=True)
if __name__ == "__main__":
    main()
