#!/usr/bin/env bash
set -euo pipefail
# Use the current checked-out source and an explicitly selected existing SDK/JDK.
# This script never chooses a host, provisions an SDK or resurrects retired paths.
: "${ANDROID_HOME:?Set ANDROID_HOME to the existing Android SDK}"
: "${JAVA_HOME:?Set JAVA_HOME to the existing JDK (17 or newer)}"
test -d "$ANDROID_HOME/platforms/android-37.0"
test -d "$ANDROID_HOME/ndk/29.0.14206865"
test -x "$ANDROID_HOME/cmake/3.22.1/bin/cmake"
test -x "$JAVA_HOME/bin/java"
if [[ -n "${ANDROID_SDK_ROOT:-}" && "$ANDROID_SDK_ROOT" != "$ANDROID_HOME" ]]; then
  echo "ANDROID_HOME and ANDROID_SDK_ROOT must name the same SDK" >&2
  exit 2
fi
export ANDROID_SDK_ROOT="$ANDROID_HOME"
vipi_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$vipi_repo_root/android"
if [ "$#" -eq 0 ]; then set -- :core:test :app:assembleDebug; fi
# Native QA: :app:assembleDebug :app:assembleDebugAndroidTest -PvipiQaAbi=x86_64
# Optimized, non-uploadable QA: :app:bundleRelease -PvipiReleaseQualification=true
# Production: :app:bundleRelease with these PRIVATE environment inputs:
# VIPI_WORKOS_CLIENT_ID, VIPI_FIREBASE_CONFIG_FILE, VIPI_UPLOAD_STORE_FILE,
# VIPI_UPLOAD_STORE_PASSWORD, VIPI_UPLOAD_KEY_ALIAS, VIPI_UPLOAD_KEY_PASSWORD.
# Release gates reject absent inputs, the known staging client and a QA ABI override.
exec ./gradlew --no-daemon --console=plain --max-workers="${VIPI_GRADLE_WORKERS:-2}" "$@"
