#!/bin/zsh
set -eu
cd "${0:A:h}/../ios"
python3 ../scripts/check-bundled-lexical.py
xcodegen generate
# XcodeGen recreates the project, so re-apply the pinned local SDK integration.
# The lock file is committed; regular builds must not update dependencies.
/opt/homebrew/bin/pod install --deployment
