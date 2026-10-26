#!/bin/zsh
# Run in the Mac's interactive login session when SSH signing cannot access the
# existing development key. This never changes keychain ACLs or passwords.
set -eu
cd /Users/Apple/Development/vipi/ios
revision=${1:?three-digit receipt revision required}
[[ "$revision" == [0-9][0-9][0-9] ]]
log="../artifacts/ipad-build-${revision}.log"
[[ ! -e "$log" ]]
zsh ../scripts/prepare-ios-project.sh
set +e
xcodebuild -workspace Vipi.xcworkspace -scheme Vipi -configuration Debug \
  -destination 'platform=iOS,id=7B6D180F-1D57-5036-8E42-C057698FBAB2' \
  -derivedDataPath ../build/ios-device -allowProvisioningUpdates build > "$log" 2>&1
status_code=$?
printf '%s\n' "$status_code" > "../artifacts/ipad-build-${revision}.exit"
tail -12 "$log"
exit "$status_code"
