# Maintaining Vipi

Work from the private integrated Git branch. Preserve the exact commit of any
build, test or publication receipt. Use the [current build environments](BUILD_ENVIRONMENTS.md)
for the Mac, emulator and private relay.

| Change | Start here |
| --- | --- |
| iOS chat header, per-chat language and accessibility | `ios/Vipi/ImmersionModeToggle.swift`, `ConversationLanguages.swift`, `ConnectedChatView.swift` and `GroupsViews.swift` |
| Android chat, vocabulary practice and language settings | `android/app/src/main/java/co/fallsoft/vipi` |
| Local voice data, supported codes and model preparation | [Local language support](LOCAL_LANGUAGE_SUPPORT.md), `scripts/build-android-speech-data.py` and the shared voice manifest under `android/app/src/main/assets/speech` |
| Encrypted delivery, capability negotiation and old-client compatibility | [Chat relay contract](CHAT_FEATURES_RELAY.md) and `backend/vipi` |
| Landing page walkthrough | `release/marketing-homepage/demo-conversation.js` for the 50 messages, `app.js` for presentation and waitlist handling, and `index.html` for page copy |
| Bluesky and Instagram draft tooling | Private `FallSoftCo/vipi-marketing` repository |

Translation capability, offline voice selection and readable transliteration are
separate checks. Clients share the voice manifest with the canonical language
and engine identifiers. Keep native playback and translation logic on each
platform. Update both native eligibility lists if a script-reading route changes.

The native messaging journey uses real app crypto and synthetic accounts. Extend
that journey when a change affects interchange. Use focused native tests for
gestures and accessibility. These results complement listening and installation
checks on a physical device.

The original service setup and in-place upgrade scripts in `ops` document
historical release paths. Use the current scoped release packet to plan a live
API, schema or worker change. Verify compatibility and existing accepted work
before replacing a service generation.

The static website can be previewed with `python3 -m http.server` from its
directory. Update the script version in `index.html` and the demo data import
version when those files change. A website content edit can change the story
independently of the animation code. Publishing and store actions are recorded
separately from source commits.
