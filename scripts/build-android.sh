#!/usr/bin/env bash
set -euo pipefail
test "$(hostname)" = ozzz-aosp
cd /aosp/development/vipi/android
export ANDROID_HOME=/aosp/ozzz-android-toolchain/sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export GRADLE_USER_HOME=/aosp/development/vipi/.cache/gradle
if [ "$#" -eq 0 ]; then set -- :core:test :app:assembleDebug; fi
exec ./gradlew --no-daemon --console=plain "$@"
