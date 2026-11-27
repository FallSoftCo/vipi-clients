# Vipi Android maintainer guide

Start from the private integrated source in the [maintenance guide](MAINTAINING_VIPI.md).
Use the [release runbook](HUMAN_RELEASE.md) for shared QA, server
deployment and store submission. This guide covers the Android build,
measurement and publication steps.

## Format Kotlin

From the repository root, run `scripts/build-android.sh formatKotlin` to
format the app and core source sets, including JVM tests, instrumented tests
and the four active Gradle Kotlin scripts. Run
`scripts/build-android.sh checkKotlinFormat` for a read-only check that fails
on differences. Both use ktfmt 0.64 with the four-space Kotlin language style
and preserve unused imports. The first run resolves ktfmt from Maven Central.
Vendor sources, generated output and historical releases are outside these
source sets.

## Toolchain and local build

Use the checked-in Gradle wrapper. The current candidate uses Gradle 9.3.1,
Android Gradle Plugin 9.1.1, Kotlin 2.4.0, Java 17 bytecode and JDK 21 for
release builds. Install Android platform `android-37.0`, NDK
`29.0.14206865` and CMake `3.22.1`. The app targets API 36 and supports
API 29 and newer. Use disk-backed worktrees, caches and outputs.

```sh
export JAVA_HOME=/path/to/jdk-21
export ANDROID_HOME=/path/to/android-sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
git status --short
git rev-parse HEAD
python3 scripts/check-client-reading-data.py
scripts/build-android.sh :core:test :app:testDebugUnitTest
scripts/build-android.sh -PvipiSourceContextQualification=true \
  -PvipiQaAbi=x86_64 :app:assembleDebug :app:assembleDebugAndroidTest
```

Run the commands from the repository root. The build script checks the exact
SDK paths and defaults to two Gradle workers. The first build needs the
declared dependencies. Use `--offline` after the required artifacts are
cached and a repeatable isolated build has succeeded. Android Studio can
import the `android` directory. Keep its Gradle JVM aligned with the shell.

The source-context option builds a separate `co.fallsoft.vipi.sourcecontextqa`
app and disables Firebase for the fixture. Use `arm64-v8a` for a dedicated
ARM64 test device. A normal debug build uses the production app ID and can
conflict with an installed Vipi. Use a dedicated emulator or an explicitly
approved handset. Keep existing apps and their local history intact.

## Navigate the code

| Area | Where to work |
| --- | --- |
| Activity and app navigation | `app/src/main/java/co/fallsoft/vipi/MainActivity.kt` receives links and notification intents. `VipiModel.kt` owns app navigation and settings state. |
| Settings and onboarding | `SettingsScreen.kt` holds the settings screen and its reusable preference rows. `MamboOnboarding.kt` and the onboarding components own the guided entry. |
| Direct and group chat | `ChatScreens.kt`, `ChatsInbox.kt` and `GroupsScreens.kt` render the UI. `ChatSession.kt` and `GroupsSession.kt` own the work that survives a screen change. |
| Keys and persistence | The `core` module contains Signal-facing message, cryptographic and persistence contracts. `MessageVault`, history backup and device recovery own durable state at their existing boundaries. |
| Attachments | `AttachmentRepository.kt`, capture UI and voice recording code own local files and playback. The relay handles encrypted bytes. |
| On-device language and speech | `ConversationTranslations.kt` owns per-chat target overrides and language-pair reuse. `ChatSession.kt` keeps access to committed direct and group history. `FullMessageTranslation.kt` and `LocalSpeech.kt` own model requests and voice playback. JNI sources are in `app/src/main/cpp`. Preserve the speech and dependency notices. |
| Auth and private records | `Authentication.kt` owns authority selection, callback and session refresh. `PrivateRecords.kt` owns the Keystore-backed file format, commit verification and removal. Reuse it for encrypted records shared with account recovery and deletion. |
| Push | `PushDelivery.kt` and the manifest own native notification registration and routing. Verify the current profile and device before exercising these paths. |

For a sign-in or encrypted-record change, run the existing
`PrivateRecordsDeviceTest`, `PrivateRecordDeletionDeviceTest` and the
identity-authority reading and exchange suites against the isolated APK.
For translation state, run `ConversationLanguagePreferencesDeviceTest` and
`InboxJourneyDeviceTest#conversationLanguageOverrideIsLocalDurableAndResettable`.
These tests exercise stored preferences and the normal conversation route.

Keep durable message and account state out of Compose functions. Changes to
delivery, ciphertext, capability negotiation or durable backup should be
tested with the relay and both native clients. A navigation, appearance or
accessibility change should be checked on normal and compact widths, with
large text when the layout depends on font scale.

## Test without changing a user's account

`core/src/test` and `app/src/test` exercise JVM behavior.
`app/src/androidTest` covers native journeys. Pick a focused class when
working on one component and run the affected journeys before review.
Use the [paired native test](../CONTRIBUTING.md#run-the-paired-native-test)
for direct and group messaging across Android and iOS.

```sh
adb devices -l
adb -s "$QA_ANDROID_SERIAL" shell pm list instrumentation
adb -s "$QA_ANDROID_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$QA_ANDROID_SERIAL" install -r android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s "$QA_ANDROID_SERIAL" shell am instrument -w \
  -e vipiDedicatedEmulator true -e vipiJourneyRun 001 \
  -e class co.fallsoft.vipi.NativeHelpDeviceTest,co.fallsoft.vipi.ConversationMotionJourneyDeviceTest,co.fallsoft.vipi.InboxJourneyDeviceTest \
  -e notClass 'co.fallsoft.vipi.InboxJourneyDeviceTest#decorativeAvatarsFitWithLargestText' \
  co.fallsoft.vipi.sourcecontextqa.test/androidx.test.runner.AndroidJUnitRunner
```

Use a fresh three-digit journey run number to keep older evidence. Before
installing, confirm that the selected serial and APK namespace are reserved
for QA. Inspect existing package names and signers. If the
device has an incompatible signer, choose another QA device or follow the
release owner's approved data-preserving procedure. Clearing, uninstalling
or replacing an app can remove local encrypted history.

Run the avatar layout case on the dedicated emulator at a font scale of at
least 1.5. In Android Settings, enlarge the font, run the case below, then
restore the original setting. Use a new run number every time.

```sh
adb -s "$QA_ANDROID_SERIAL" shell am instrument -w \
  -e vipiDedicatedEmulator true -e vipiJourneyRun 002 \
  -e class 'co.fallsoft.vipi.InboxJourneyDeviceTest#decorativeAvatarsFitWithLargestText' \
  co.fallsoft.vipi.sourcecontextqa.test/androidx.test.runner.AndroidJUnitRunner
```

If a fresh emulator reports a startup ANR while it verifies bytecode, inspect
its original logcat and outcome. On the dedicated emulator only, precompile
the two installed QA packages with
`adb -s "$QA_ANDROID_SERIAL" shell cmd package compile -m speed -f PACKAGE`
and run with a new result number. Use the isolated app and test package IDs
from the install above. [AndroidJUnitRunner filters](https://developer.android.com/reference/androidx/test/runner/AndroidJUnitRunner)

For a production-device check, use the controlled shared-authority account
and current registered-device state from the release record. The app can
request a new device registration immediately after a successful profile
lookup. Inspect registration or reauthentication outcomes before taking
another action. Keep counterpart test messages and recipients controlled.

## Build and review the store artifact

Use a clean worktree. Read the current Play release and version codes before
choosing the candidate. The release command reads the existing operator-owned signing files and
registered Firebase configuration. It derives the public WorkOS client ID from
the source. See [signing input status and refresh](RELEASE_ACCESS.md#android-signing).

```sh
python3 scripts/build-android-release.py --check
python3 scripts/build-android-release.py
jarsigner -verify android/app/build/outputs/bundle/release/app-release.aab
sha256sum android/app/build/outputs/bundle/release/app-release.aab
```

Record the exact artifact digest, app ID, version code, version name, source
revision, expected signing fingerprint and the complete tested ABI set.
Keep native debug symbols and mapping files with the candidate. The release
build checks its production client, Firebase project and the upload signing
inputs. Leave off the QA switches and any ABI restriction when preparing
the store bundle. Confirm the source archive and license notices against
the actual signed application.

Open the owned Vipi app in Play Console and check the internal track and
bundle history first. Select or upload the exact bundle for the intended
eligible internal testers and verify processing. Inspect the current Play
app-signing fingerprint through App Integrity. It is the fingerprint used
by Digital Asset Links. Play's internal app sharing signs development
uploads with a separate certificate.

Install through the eligible internal test link on the intended handset.
Check the installed version and installer, then inspect the app's identity
and domain routing without modifying link preferences.

```sh
adb -s "$QA_ANDROID_SERIAL" shell dumpsys package co.fallsoft.vipi
adb -s "$QA_ANDROID_SERIAL" shell pm get-app-links co.fallsoft.vipi
```

On that same build, verify fresh sign-in, the expected friend-link target,
sent and received messages, lock-screen push and correct routing after
tapping a notification. Check ordinary on-device preferences for preview
visibility. A provider delivery acknowledgment alone does not prove the
visible handset behavior.

Verify the current submitting track, app record, pending changes and managed
publishing setting before sending anything for review. Record the original
result and read it back if the response is interrupted. Use the
[shared publication runbook](HUMAN_RELEASE.md) for submission and
publication.

[Play internal testing](https://support.google.com/googleplay/android-developer/answer/9845334)
and [internal app sharing](https://support.google.com/googleplay/android-developer/answer/9844679)
describe the current distribution paths.
