#!/usr/bin/env python3
"""Build the bounded native corpus probe in the existing authorized Apple VM."""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--module-cache', type=Path)
a = p.parse_args()
if platform.system() != 'Darwin':
    raise SystemExit('Build only in the existing Apple development VM.')
root = Path(__file__).resolve().parents[2]
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
base = ['xcrun', 'swiftc', '-parse-as-library', '-O', '-DDEBUG', '-target', 'arm64-apple-macosx26.4',
        '-sdk', sdk, '-module-cache-path', str(a.module_cache or out / 'ModuleCache')]
core = sorted((root / 'ios/VipiCore/Sources/VipiCore').glob('*.swift'))
subprocess.run(base + ['-emit-library', '-emit-module', '-module-name', 'VipiCore',
    '-emit-module-path', str(out / 'VipiCore.swiftmodule'), '-Xlinker', '-install_name',
    '-Xlinker', '@rpath/libVipiCore.dylib', *map(str, core), '-o', str(out / 'libVipiCore.dylib')], check=True)
# Extract unchanged value definitions, excluding unrelated SwiftUI application code.
definitions = []
for filename, begin, end in [
    ('AppState.swift', 'struct VipiLanguage:', '\nenum OnboardingStep:'),
    ('LanguageDownloadView.swift', 'struct TranslationPair:', '\nenum LocalLanguageAvailability:'),
    ('VocabularyPack.swift', 'enum VocabularyPackError:', '\n')]:
    text = (root / 'ios/Vipi' / filename).read_text()
    start = text.index(begin)
    finish = text.index(end, start)
    definitions.append(text[start:finish])
shim = out / 'ProductionValueDefinitions.swift'
shim.write_text('import Foundation\n' + '\n'.join(definitions) + '\n')
names = ['LocalImmersion', 'BundledImmersionCatalog', 'BundledLexicalCatalog',
         'LexicalConcordance', 'ContextWitnessLookup', 'ReviewedFrameLookup',
         'ReviewedContextLookup', 'ReviewedContextRecord', 'SentenceReadings']
native = [root / 'ios/Vipi' / (name + '.swift') for name in names]
probe = root / 'qa/immersion/MacLiveImmersionProbe.swift'
subprocess.run(base + ['-I', str(out), '-L', str(out), '-lVipiCore', '-Xlinker', '-rpath',
    '-Xlinker', '@executable_path', str(shim), *map(str, native), str(probe),
    '-o', str(out / 'vipi-live-immersion-probe')], check=True)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
sources = core + native + [probe, Path(__file__).resolve()]
receipt = {'sdk': sdk, 'system': platform.platform(), 'source_sha256': {
    str(path.relative_to(root)): sha(path) for path in sources},
    'extracted_value_definitions_sha256': sha(shim),
    'runner_sha256': sha(out / 'vipi-live-immersion-probe'),
    'limits': ['SentenceReadings uses Bundle.main resources; a CLI must be bundled with the exact sentence-readings.json to exercise complete non-Roman reference readings.',
               'Explicit language pairs bypass classification. No model downloads. No physical-device or offline acceptance.']}
(out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
