#!/bin/zsh
set -eu
cd "${0:A:h}/../ios"
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
log="../artifacts/ipad-swahili-coverage-${revision}.log"
[[ ! -e "$log" ]]
zsh ../scripts/prepare-ios-project.sh
set +e
TEST_RUNNER_VIPI_SWAHILI_CORPUS=1 xcodebuild -workspace Vipi.xcworkspace -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  -only-testing:VipiCryptoTests/SwahiliConversationCoverageTests \
  -resultBundlePath "../artifacts/ipad-swahili-coverage-${revision}.xcresult" test > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-swahili-coverage-${revision}.exit"
tail -12 "$log"
exit "$status_code"
