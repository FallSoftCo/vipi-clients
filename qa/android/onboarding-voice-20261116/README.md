# Onboarding speech recovery

The selected-language preview prepares the actual selected pair, not all eleven voices at once. Earlier offline matrix testing rendered all 110 directions on this QA emulator; voice installation and readiness can differ on other devices.

The controlled Compose device test injects an unavailable voice and a failed speech-settings launch, verifies the settings fallback instruction and retry action at 2× text in dark theme, and confirms retry transitions out of the unavailable state. It does not claim TalkBack traversal, real permission denial, or physical-device acoustic acceptance. The first attempted in-place install failed without changing the installed app; a confirmed retry succeeded and protected app files matched the pre-install snapshot. An initial combined UI test ran against the previous APK and failed; it is not counted as evidence for this change.
