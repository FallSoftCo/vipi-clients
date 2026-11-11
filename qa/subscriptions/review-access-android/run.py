#!/usr/bin/env python3
"""Compile the actual JSON access models with cached Kotlin; no Android build or network."""
from pathlib import Path
import argparse, hashlib, json, subprocess
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--cache', type=Path, default=Path.home()/'.gradle/caches/modules-2/files-2.1')
a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parents[3]
source = root/'android/app/src/main/java/co/fallsoft/vipi/Subscriptions.kt'
text = source.read_text()
models = 'package co.fallsoft.vipi\nimport org.json.JSONObject\nimport java.time.Instant\n' + text[text.index('internal enum class SubscriptionPlan'):text.index('internal data class SubscriptionOffer')]
model = a.output/'ActualAccessModels.kt'; model.write_text(models)
def jar(group, artifact, version):
    hits = list((a.cache/group/artifact/version).glob('*/*.jar'))
    assert len(hits) == 1, (group, artifact, version)
    return str(hits[0])
stdlib = jar('org.jetbrains.kotlin', 'kotlin-stdlib', '2.4.0')
annotations = jar('org.jetbrains', 'annotations', '13.0')
js = jar('org.json', 'json', '20240303')
compiler = [jar('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '2.4.0'), stdlib,
    jar('org.jetbrains.kotlin', 'kotlin-script-runtime', '2.4.0'),
    jar('org.jetbrains.kotlin', 'kotlin-reflect', '1.6.10'),
    jar('org.jetbrains.intellij.deps', 'trove4j', '1.0.20200330'),
    jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.10.2'), annotations]
classes = a.output/'classes'
cmd = ['java', '-XX:ActiveProcessorCount=2', '-Xmx512m', '-cp', ':'.join(compiler),
    'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect', '-jvm-target', '17',
    '-classpath', ':'.join([stdlib, annotations, js]), '-d', str(classes), str(model),
    str(Path(__file__).with_name('PlanAccessTest.kt'))]
subprocess.run(cmd, check=True)
result = subprocess.check_output(['java', '-XX:ActiveProcessorCount=2', '-cp', ':'.join([str(classes),stdlib,js]),
    'co.fallsoft.vipi.PlanAccessTestKt'], text=True)
(a.output/'receipt.json').write_text(json.dumps({'pass':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'actual_model_sha256':hashlib.sha256(models.encode()).hexdigest(),'result':result.strip(),
    'scope':'Actual model compiled; no native UI/device build, install or provider calls'},indent=2)+'\n')
print(result.strip())
