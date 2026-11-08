#!/usr/bin/env python3
"""Export the committed native controls, never the working tree experiments.

The generated functions retain the exact production bodies. The surrounding
wrapper only removes unused SQLite/app dependencies for the macOS QA CLI.
This exports source; it does not compile, execute, or activate a data provider.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(repository, revision, output):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repository), *args])

    commit = git("rev-parse", f"{revision}^{{commit}}").decode().strip()
    contract_path = "qa/immersion/nlp-template-comparison-r01/contract.json"
    contract_bytes = (repository / contract_path).read_bytes()
    contract_hash = sha(contract_bytes)
    if contract_hash != "3767a5f794023ff1fef85f5120658ce7881be0c143fd2357dcfcfe705272fdf2":
        raise ValueError("Unexpected comparison contract")
    contract = json.loads(contract_bytes)
    # The committed partial-verb guard is retained; uncommitted experiments are
    # intentionally not a source for this comparison.
    subprocess.run(["git", "-C", str(repository), "merge-base", "--is-ancestor",
                    "a27eff2", commit], check=True)
    if output.exists():
        raise FileExistsError(output)
    paths = git("ls-tree", "-r", "--name-only", commit,
                "ios/VipiCore/Sources/VipiCore").decode().splitlines()
    contents = {path: git("show", f"{commit}:{path}") for path in paths if path.endswith(".swift")}
    for path in ["ios/Vipi/LocalImmersion.swift", "ios/Vipi/ReviewedFrameLookup.swift",
                 "ios/Vipi/BundledImmersionCatalog.swift", "ios/Vipi/SentenceReadings.swift",
                 "ios/Vipi/AppState.swift", "ios/Vipi/LanguageDownloadView.swift",
                 "ios/Vipi/VocabularyPack.swift", "data/immersion/catalog.json",
                 "data/examples/sentence-readings.json"]:
        contents[path] = git("show", f"{commit}:{path}")
    for path, data in contents.items():
        if path in contract["baseline_source"] and sha(data) != contract["baseline_source"][path]:
            raise ValueError(f"Committed control differs from frozen contract: {path}")

    local = contents["ios/Vipi/LocalImmersion.swift"].decode()
    local_body = local[local.index("enum LocalImmersion {"):local.index("    static func align(")]
    frame = contents["ios/Vipi/ReviewedFrameLookup.swift"].decode()
    frame_body = frame[frame.index("    /// Native word windows"):frame.index("    private static func frame(")]
    generated = ("// QA wrapper extracted from the exact committed source bodies.\n"
                 "import Foundation\nimport CoreFoundation\nimport NaturalLanguage\n\n"
                 + local_body + "}\n\nenum ReviewedFrameLookup {\n" + frame_body + "}\n").encode()
    values = []
    for name, begin, end in [
        ("AppState.swift", "struct VipiLanguage:", "\nenum OnboardingStep:"),
        ("LanguageDownloadView.swift", "struct TranslationPair:", "\nenum LocalLanguageAvailability:"),
        ("VocabularyPack.swift", "enum VocabularyPackError:", "\n")]:
        text = contents["ios/Vipi/" + name].decode()
        start = text.index(begin)
        values.append(text[start:text.index(end, start)])
    catalog = contents["ios/Vipi/BundledImmersionCatalog.swift"].decode()
    catalog = catalog[catalog.index("actor BundledImmersionCatalog {"):catalog.index("    func result(")] + "}\n"
    readings = contents["ios/Vipi/SentenceReadings.swift"].decode()
    readings = readings[readings.index("enum SentenceReadings {"):readings.index("\n/// Full-text display metadata")]
    references = ("// QA extraction: source-reference functions and value declarations unchanged.\n"
                  "import Foundation\nimport CryptoKit\n\n" + "\n".join(values)
                  + "\n\n" + catalog + "\n" + readings).encode()
    output.mkdir(parents=True)
    for path, data in contents.items():
        destination = output / "production" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (output / "NativeBoundaries.swift").write_bytes(generated)
    (output / "NativeReferences.swift").write_bytes(references)
    manifest = {
        "schema": "vipi.apple-nlp-clean-controls.1", "commit": commit,
        "contract_sha256": contract_hash,
        "production_source": {path: sha(data) for path, data in sorted(contents.items())},
        "generated_source": {"NativeBoundaries.swift": sha(generated),
                             "NativeReferences.swift": sha(references)},
        "extraction": {
            "LocalImmersion": "Exact sentences/words function bodies; align omitted",
            "ReviewedFrameLookup": "Exact windows function body; SQLite lookup omitted",
            "BundledImmersionCatalog": "Exact reference/partial functions; target-dependent lookup omitted",
            "SentenceReadings": "Exact authored reading enum; no fallback reading invoked",
            "value_definitions": "Exact VipiLanguage/TranslationPair/VocabularyPackError declarations"},
        "working_tree_read_for_production_source": False,
        "default_source_unit_provider_activated": False,
        "actual_translation_provider_calls": 0,
        "limits": "Explicit source language; source-only CLI controls, not app orchestration or automatic language identification. Whole-reference availability does not claim execution of target-dependent alignment."
    }
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.repository, args.commit, args.output)
    print(json.dumps({"commit": result["commit"], "files": len(result["production_source"]),
                      "output": str(args.output)}))
