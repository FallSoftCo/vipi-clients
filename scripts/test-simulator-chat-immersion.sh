#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
run="${1:?three-digit run identifier required}"
[[ "$run" =~ ^[0-9]{3}$ ]]
method="${2:-ChatImmersionTests}"
[[ "$method" =~ ^ChatImmersionTests(/[A-Za-z0-9_]+)?$ ]]
log="artifacts/simulator-chat-immersion-$run.log"
result="artifacts/simulator-chat-immersion-$run.xcresult"
test ! -e "$log" && test ! -e "$result"
# ML Kit has no arm64 simulator slice. VipiSimulator explicitly reports that
# adapter unavailable; these are real UI/catalog tests, not model tests.
# Ad-hoc signing is required for the synthetic account's Keychain entitlement.
zsh scripts/prepare-ios-project.sh
cd ios
xcodebuild -workspace Vipi.xcworkspace -scheme VipiSimulator -configuration Simulator -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,id=46CB569D-EA59-40E3-82CC-F4A0F36EDB87,arch=arm64' \
  -derivedDataPath ../build/ios-simulator -parallel-testing-enabled NO -collect-test-diagnostics never \
  "-only-testing:VipiUITests/$method" -resultBundlePath "../$result" \
  ARCHS=arm64 EXCLUDED_ARCHS= CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- test > "../$log" 2>&1
