#!/bin/zsh
set -eu
cd "${0:A:h}/../ios"
python3 prepare-libsignal.py
python3 ../scripts/check-bundled-lexical.py
xcodegen generate
# XcodeGen recreates the project, so re-apply the pinned local SDK integration.
# The lock file is committed; regular builds must not update dependencies.
/opt/homebrew/bin/pod install --deployment
# The generated projects are ignored; retain the actual qualified Swift package
# pins in source and put them in the workspace consumed by xcodebuild.
mkdir -p Vipi.xcworkspace/xcshareddata/swiftpm
cp Package.resolved Vipi.xcworkspace/xcshareddata/swiftpm/Package.resolved
