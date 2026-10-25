#!/bin/zsh
set -eu
cd /Users/Apple/Development/vipi/ios
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
test_name=${2:-testPrepareAndRunAppleTranslation}
case "$test_name" in
  testPrepareAndRunAppleTranslation|testInspectNetworkControls|testRunAppleTranslationWithoutNetwork) ;;
  *) exit 2 ;;
esac
log="../artifacts/ipad-translation-${revision}.log"
[[ ! -e "$log" ]]
xcodegen generate
set +e
xcodebuild -project Vipi.xcodeproj -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  "-only-testing:VipiUITests/TranslationDeviceTests/$test_name" \
  -resultBundlePath "../artifacts/ipad-translation-${revision}.xcresult" test > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-translation-${revision}.exit"
tail -12 "$log"
exit "$status_code"
