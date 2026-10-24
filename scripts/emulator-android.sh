#!/usr/bin/env bash
set -euo pipefail
test "$(hostname)" = ozzz-aosp
export ANDROID_HOME=/aosp/ozzz-android-toolchain/sdk
export ANDROID_AVD_HOME=/aosp/development/vipi/.runtime/avds
export ANDROID_EMULATOR_HOME=/aosp/development/vipi/.runtime/emulator
mkdir -p "$ANDROID_EMULATOR_HOME"
exec "$ANDROID_HOME/emulator/emulator" -avd vipi-api35-20261024 -port 5620 -no-window -no-audio -no-boot-anim -no-snapshot -no-metrics -skip-adb-auth -accel on -cores 2 -memory 3072 -gpu swiftshader_indirect -camera-back none -camera-front none -netdelay none -netspeed full
