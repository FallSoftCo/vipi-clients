# Native Android source and build inputs

Use the current source authority and existing Android environment described in
`../docs/BUILD_ENVIRONMENTS.md`. Retired host commands in historical receipts
are not current build instructions. Do not create a replacement QA VM or clear
an existing app's data to reproduce a build.

The checked-in wrapper pins Gradle 9.3.1 and its distribution SHA-256. The source
pins AGP 9.1.1, Kotlin/Compose compiler 2.4.0 and R8 9.5.28. Android compilation
uses SDK 37, minimum API 29, target API 36, NDK 29.0.14206865 and CMake 3.22.1.
Java/Kotlin bytecode targets Java 17; the `core` module requests a Java 17
toolchain. Use an existing compatible JDK and SDK, with capacity admitted for
dependencies, generated assets, C++ outputs, APKs and temporary files.

Set `JAVA_HOME` and `ANDROID_HOME` to those existing installations.
`ANDROID_SDK_ROOT`, if set, must name the same SDK. The repository helper checks
these paths and defaults to two Gradle workers. It does not install an SDK or
select a host. From the repository root:

```sh
scripts/build-android.sh :core:test :app:assembleDebug
```

For the existing x86_64 QA emulator, build its matching test APK explicitly:

```sh
scripts/build-android.sh -PvipiQaAbi=x86_64 \
  :app:assembleDebug :app:assembleDebugAndroidTest
```

Select only the owned emulator serial and relevant instrumented test classes.
Native tests can create accounts, import fixtures or alter app state; inspect
their setup and retained receipts before running them against a signed-in app.
The API 35 emulator does not establish API 29 or physical 16-KiB-page support.

## Required language and speech assets

Gradle stages the live Mandarin reading table from `data/readings` and the
client license and notices. ML Kit downloads the selected translation models
through its on-device model manager. A fresh install can translate offline
after the required model download succeeds.

The fallback voice assets and their manifest are checked in under
`app/src/main/assets/speech`. The manifest maps each supported language to
its pinned eSpeak voice and dictionary. Android first looks for an installed
offline voice. See `../docs/LOCAL_LANGUAGE_SUPPORT.md` for the supported
language choices and their device-specific requirements.

eSpeak NG and Sonic source are retained under `android/vendor`, with exact
revisions in `speech-provenance.json`. JNI/CMake inputs live in
`app/src/main/cpp`. Use `scripts/build-android-speech-data.py` from the repo
root to reproduce the fallback data. Retain the voice inputs and licenses,
including the Kuromoji IPADIC dictionary used for Japanese readings.

## Qualification and production releases

An optimized qualification bundle uses a distinct application ID and the local
debug certificate. It intentionally has no production auth configuration:

```sh
scripts/build-android.sh -PvipiReleaseQualification=true :app:bundleRelease
```

**Never upload a qualification bundle.** Preserve its exact source/binary hashes
and identify it as qualification evidence. Earlier size, ABI and alignment
checks apply to their recorded artifacts, not automatically to a later release.

A production bundle requires these release-environment inputs:

- `VIPI_WORKOS_CLIENT_ID`: the public production client identifier.
- `VIPI_FIREBASE_CONFIG_FILE`: the matching registered Firebase configuration.
- `VIPI_UPLOAD_STORE_FILE`, `VIPI_UPLOAD_STORE_PASSWORD`,
  `VIPI_UPLOAD_KEY_ALIAS`, `VIPI_UPLOAD_KEY_PASSWORD`: private signing inputs.

Supply private values through the existing secret environment, without printing
them or putting them on a shell command line. Do not commit local configuration,
keystores, signing passwords, QA sessions or account fixtures. The release gate
rejects missing inputs, the known staging client and the qualification ABI
override. With the actual configuration already loaded:

```sh
scripts/build-android.sh :app:bundleRelease
```

Record the resulting version, certificate and file hash. Verify production auth,
background push, provider behavior, release shrinking and the
required device/ABI behavior before upload. `release/STORE_SUBMISSION.md` records
the separate store gates. A successful compiler or signature check does not
establish those external behaviors.

## Dependencies and corresponding source

The app pins libsignal-android 0.105.0 from Signal's Maven repository;
the corresponding upstream source is commit
`4beb029d8a941f81e7d9c6d8af1ed25a677569a8`. Desktop/JNI-test binaries are excluded
from packaging. Preserve the complete upstream source, build inputs, transitive
locks and acknowledgments with the release source closure.

Resolved artifact hashes and embedded notice texts are in
`app/src/main/assets/legal/third-party/index.json`; additional pinned license
texts are under `legal/upstream`. Settings exposes these notices. To regenerate
the inventory after an intentional dependency change:

```sh
scripts/build-android.sh -I ../scripts/android-dependency-inventory.gradle \
  :app:vipiDependencyInventory
python3 scripts/collect-android-notices.py
```

These commands use the normal build directory. A build with a relocated output
directory must pass its actual inventory path to the collector. Review changed
coordinates, hashes and notices before staging them. Exact direct versions and
an artifact inventory do not by themselves establish a complete Gradle
dependency-verification policy or a fresh-machine reproducible build; those
remain separate release checks.

`LICENSE` and `NOTICE` describe the client license. They do not relicense Google
SDKs or language data. Publish the reviewed client source/build inputs and exact
corresponding dependency sources required by the shipped combination, preserving
each component's notices. Private backend/operations history, credentials and
research conversations are outside that public client export. No public source
release or app-store submission is established by this document.
