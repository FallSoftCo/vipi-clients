#!/bin/zsh
set -eu
cd "${0:A:h}/../ios"
command -v xcodegen >/dev/null || { print -u2 'XcodeGen 2.46.0 is required in PATH.'; exit 1; }
command -v pod >/dev/null || { print -u2 'CocoaPods 1.17.0 is required in PATH; retain the committed Podfile.lock.'; exit 1; }
python3 prepare-libsignal.py
python3 ../scripts/check-client-reading-data.py
xcodegen generate
# XcodeGen recreates the project, so re-apply the pinned local SDK integration.
# The lock file is committed; regular builds must not update dependencies.
pod install --deployment
# The generated projects are ignored; retain the actual qualified Swift package
# pins in source and put them in the workspace consumed by xcodebuild.
mkdir -p Vipi.xcworkspace/xcshareddata/swiftpm
cp Package.resolved Vipi.xcworkspace/xcshareddata/swiftpm/Package.resolved
