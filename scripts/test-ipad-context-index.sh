#!/bin/zsh
set -eu
cd /Users/Apple/Development/vipi/ios
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
log="../artifacts/ipad-context-index-${revision}.log"
[[ ! -e "$log" ]]
zsh ../scripts/prepare-ios-project.sh
set +e
xcodebuild -workspace Vipi.xcworkspace -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  -only-testing:VipiCryptoTests/ContextIndexTests \
  -resultBundlePath "../artifacts/ipad-context-index-${revision}.xcresult" test > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-context-index-${revision}.exit"
tail -12 "$log"
exit "$status_code"
