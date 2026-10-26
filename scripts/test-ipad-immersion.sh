#!/bin/zsh
set -eu
cd /Users/Apple/Development/vipi/ios
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
log="../artifacts/ipad-immersion-${revision}.log"
[[ ! -e "$log" ]]
case "${2:-all}" in
  all) tests=(-only-testing:VipiUITests/ContinuousImmersionTests -only-testing:VipiUITests/LanguageReadingTests -only-testing:VipiUITests/SpeechInteractionTests) ;;
  reading) tests=(-only-testing:VipiUITests/LanguageReadingTests/testJapaneseReadingScriptAndGrammarStayInOneBubble) ;;
  *) exit 2 ;;
esac
zsh ../scripts/prepare-ios-project.sh
set +e
xcodebuild -workspace Vipi.xcworkspace -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  "${tests[@]}" \
  -resultBundlePath "../artifacts/ipad-immersion-${revision}.xcresult" test > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-immersion-${revision}.exit"
tail -12 "$log"
exit "$status_code"
