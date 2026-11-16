#!/bin/bash
set -eu
b=/Users/Apple/Development/vipi-native-delivery-20261109-r01;w=$b/resume-20261116-lookup-r01;o=$b/unsigned-simulator-probe-r19;r=$o/speech-matrix-r74
mkdir "$r"
free=$(df -Pk "$o" | awk 'NR==2 {print $4}');test "$free" -ge 4718592 || { echo disk_budget_failed > "$r/status";exit 1; }
if pgrep -x xcodebuild >/dev/null;then echo build_busy > "$r/status";exit 1;fi
test "$(shasum -a 256 "$w/speech-matrix-r74.tar.gz" | cut -d' ' -f1)" = d74f1a8f1ea343d185e4a005b0c9f8826a1cfae7b7e50d91ed8c8f8aa53d9a2f
mkdir "$r/overlay";tar -xzf "$w/speech-matrix-r74.tar.gz" -C "$r/overlay"
cp "$o/source/ios/Vipi/VipiApp.swift" "$r/prior-QA-entry.swift"
cp "$o/source/ios/Vipi/MessageVault.swift" "$r/prior-QA-vault.swift"
cp "$r/overlay/qa/macos/apple-resume-20261116-r01/SpeechMatrixSimulatorQAMain.swift" "$o/source/ios/Vipi/VipiApp.swift"
cp "$o/simulator-qa-r37/prior-MessageVault.swift" "$o/source/ios/Vipi/MessageVault.swift"
find "$o/source/ios/Vipi" "$o/source/ios/VipiCore/Sources/VipiCore" -name '*.swift' -type f -exec shasum -a 256 {} \; | sort > "$r/source-sha256.txt"
echo building > "$r/status"
cd "$o/source/ios"
xcodebuild -workspace Vipi.xcworkspace -scheme VipiSimulator -configuration Simulator -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath "$o/DerivedData" -clonedSourcePackagesDirPath "$o/SourcePackages" -disableAutomaticPackageResolution -onlyUsePackageVersionsFromResolvedFile -skipPackageUpdates -jobs 2 ARCHS=arm64 ONLY_ACTIVE_ARCH=YES PRODUCT_BUNDLE_IDENTIFIER=co.fallsoft.vipi.speechmatrixqa CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY= CODE_SIGN_STYLE=Manual PROVISIONING_PROFILE_SPECIFIER= build > "$r/build.log" 2>&1 || { echo build_failed > "$r/status";exit 1; }
echo built > "$r/status"
