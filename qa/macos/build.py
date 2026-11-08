#!/usr/bin/env python3
"""Build the macOS app and runner inside the existing Apple development VM."""
import argparse, hashlib, json, pathlib, platform, plistlib, subprocess
parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True, type=pathlib.Path)
parser.add_argument("--module-cache", type=pathlib.Path)
args = parser.parse_args()
if platform.system() != "Darwin":
    raise SystemExit("Requires the existing Apple development VM and its Apple SDK.")
root = pathlib.Path(__file__).resolve().parents[2]
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
source = root / "qa/macos"
original = (root / "ios/Vipi/LocalImmersion.swift").read_text()
# Compile the exact production tokenizer without its downstream immersion engine.
prefix = original.split("    static func align(", 1)[0]
assert prefix != original and "static func words(" in prefix
tokenizer = out / "LabTokenizer.swift"
tokenizer.write_text(prefix.replace("import VipiCore\n", "").replace("enum LocalImmersion {", "enum LabTokenizer {") + "}\n")
bundle = out / "Vipi Immersion Lab.app"
contents = bundle / "Contents"
macos = contents / "MacOS"
macos.mkdir(parents=True)
plist = {
    "CFBundleName": "Vipi Immersion Lab", "CFBundleDisplayName": "Vipi Immersion Lab",
    "CFBundleIdentifier": "co.fallsoft.vipi.immersionlab",
    "CFBundleExecutable": "VipiImmersionLab", "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "0.1", "CFBundleVersion": "1",
    "LSMinimumSystemVersion": "26.4", "NSHighResolutionCapable": True,
}
(contents / "Info.plist").write_bytes(plistlib.dumps(plist))
sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
common = ["xcrun", "swiftc", "-parse-as-library", "-O", "-j2", "-target", "arm64-apple-macosx26.4",
          "-sdk", sdk, "-module-cache-path", str(args.module_cache or out / "ModuleCache"), str(tokenizer), str(source / "Comparison.swift")]
subprocess.run(common + [str(source / "App.swift"), "-o", str(macos / "VipiImmersionLab")], check=True)
subprocess.run(common + [str(source / "Batch.swift"), "-o", str(out / "vipi-translation-compare")], check=True)
subprocess.run(["codesign", "--force", "--sign", "-", str(bundle)], check=True)
subprocess.run(["codesign", "--verify", "--strict", str(bundle)], check=True)
sources = [root / "ios/Vipi/LocalImmersion.swift", *sorted(source.glob("*.swift")), pathlib.Path(__file__).resolve()]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
receipt = {"platform": platform.platform(), "source_sha256": {str(p.relative_to(root)): sha(p) for p in sources},
           "app_executable_sha256": sha(macos / "VipiImmersionLab"),
           "batch_executable_sha256": sha(out / "vipi-translation-compare"),
           "tokenizer_sha256": sha(tokenizer), "sdk": sdk, "ad_hoc_signed": True,
           "app": str(bundle), "runner": str(out / "vipi-translation-compare")}
(out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
