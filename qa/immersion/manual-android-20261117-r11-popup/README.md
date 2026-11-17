# Production-popup real-provider check: failed Stop, r11

The production app remains exact r10; only the test APK changed to mount the actual ManualLookupPopup and assert visible target text. Installed hashes were independently verified and are retained here. Only the owned emulator 5624 and `.uxqa` package were used, with existing Spanish model and no downloads. Prior narrower successful r10 evidence remains unchanged.

The strengthened case ran for 12.709 seconds and **failed** at the same-word Stop step. It first established all of the following: one native uncovered book tap; exactly one real ML Kit call with the complete English sentence; Spanish output using reservar; the exact actual target displayed in Compose semantics; a readable production popup screenshot; and actual Spanish-script SpeechPlayback entering PLAYING. Tap-to-playing was 1,106 ms.

With the popup present, tapping the same word again produced a second accepted speech input instead of cancelling the interaction. The popup/request remained visible and the test timed out waiting for Stop. Provider calls remained one: this was cached replay, not another translation. The later cached whole-message gesture was not reached and is not accepted by this stronger run.

The likely route is popup outside-dismiss cancelling before the pass-through native text gesture can preserve its stop marker, allowing the same tap to start a new cached request. This is a source-based hypothesis; the observed duplicate speech and failed cancellation are recorded facts. UX owns diagnosis/fix; no production source was changed by this qualification agent. No final gesture acceptance or acoustic-quality claim is made.

The same cumulative 20 MiB allowance and exact 4,504,682,496-byte floor were retained. No guard stop or model download occurred. Raw receipt is included; its net allocation remained below the earlier baseline. The native screenshots were inspected: Spanish translation appears clearly, and the failed Stop leaves the popup present. Device ownership was released to UX after receipt capture.
