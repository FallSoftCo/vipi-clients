#!/bin/zsh
set -eu
cd /Users/Apple/Development/vipi/ios
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
log="../artifacts/ipad-translation-${revision}.log"
[[ ! -e "$log" ]]
xcodegen generate
set +e
xcodebuild -project Vipi.xcodeproj -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates \
  -parallel-testing-enabled NO -only-testing:VipiUITests/TranslationDeviceTests \
  -resultBundlePath "../artifacts/ipad-translation-${revision}.xcresult" test > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-translation-${revision}.exit"
tail -12 "$log"
exit "$status_code"
