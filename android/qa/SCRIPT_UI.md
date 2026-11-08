# Native script interaction qualification

`ScriptConversationInteractionTest` exercises the production conversation, inline renderer and local speech through the native frame clock. Its contact and relay are isolated synthetic fixtures; messages honestly remain waiting to send. It does not establish network delivery, unseen linguistic accuracy, acoustic quality or physical-device behavior.

The eight frozen catalog examples cover English to/from Arabic, Japanese, Korean and Chinese. Forward cases use light appearance and system font scale 1.0; reverse cases use dark appearance and scale 1.8. The test measures four automatic changes, source glyph anchors and view bounds, original-script/transliteration switching, actual audio playback and unchanged cache reuse, draft pause, empty focused composer resume, and history scroll/return. Initial and keyboard geometry must settle within eight seconds before measurement. Public reference lookup is prewarmed and is not a cold-start measurement.

Use an explicitly assigned existing emulator with the current debug app and test APK. Preserve its app data, existing account and original system settings. Do not use this fixture on an unrelated active device. The dedicated-emulator argument is mandatory. Stage the unchanged protocol into the app files directory using `adb push` followed by `run-as co.fallsoft.vipi cp`; retain its SHA-256. No language or voice downloads are requested by the fixture preflight.

Run the target after setting the family’s actual system font scale:

```sh
adb -s "$VIPI_QA_SERIAL" shell am instrument -w \
  -e class co.fallsoft.vipi.ScriptConversationInteractionTest \
  -e vipiDedicatedEmulator true \
  -e vipiScriptFamily reverse -e vipiScriptRun 001 \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
```

Use a fresh three-digit run ID; existing output must never be overwritten. An optional `-e vipiScriptCase ar-en` limits a follow-up to one exact case in that family. Output is `files/script-conversation-<family>-<run>/receipt.json` and actual screenshots, exportable with `run-as`. Preserve incomplete receipts and failed harness provenance as well as passing cases. Restore the original system font scale and input settings in a host-side `finally` block. A live system-font change needs a separate actual app restoration test because Android recreates the activity; launch-at-large alone does not prove it.
