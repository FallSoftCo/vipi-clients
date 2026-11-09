# Current-source iOS development build

Committed source `ef76d35` builds and signs for iOS arm64 under the Fallible Software team, using the existing native Mac. This includes the default Japanese/Swahili starters and privacy packaging fix. The app passes strict recursive signature verification, contains all 13 privacy manifests, and retains byte-verified language assets. The 66 generated lexical files are verified against the committed catalog; they are intentionally absent from Git.

Only build-time development signing settings differ from the committed project: the app uses its explicit profile, and test targets use the existing Xcode-managed wildcard profile. Initial generated-resource staging and manual-versus-managed test-profile failures are retained. No source, keychain ACL, account, network setting or store record was changed to make the build pass.

This is a development build, not an App Store archive or release signature. An attempted iPad UI test had already exited unsuccessfully before the owner instructed Vipi to leave the iPad to 8bar Club. Existing preference values remained unchanged. That result is not accepted and will not be rerun on the device. Current/future Vipi validation uses the existing simulators and native Mac; old physical-device commands are historical evidence.
