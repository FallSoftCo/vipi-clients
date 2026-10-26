#!/bin/zsh
set -eu
cd /Users/Apple/Development/vipi/ios
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
mode=${2:-all}
[[ "$mode" == all || "$mode" == capture ]]
selection=(-only-testing:VipiCryptoTests/FrameCaptureTests)
if [[ "$mode" == all ]]; then selection+=(-only-testing:VipiCryptoTests/ReviewedFramePackTests); fi
log="../artifacts/ipad-reviewed-frames-${revision}.log"
[[ ! -e "$log" ]]
zsh ../scripts/prepare-ios-project.sh
set +e
xcodebuild -workspace Vipi.xcworkspace -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  "${selection[@]}" \
  -resultBundlePath "../artifacts/ipad-reviewed-frames-${revision}.xcresult" test > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-reviewed-frames-${revision}.exit"
tail -12 "$log"
exit "$status_code"
