# Android localization and cardless access — draft

This isolated branch is incomplete and must not be released or used as evidence of full localization. It does not change the uploaded Android artifact.

The UI uses Android OS locale resources independently of the immersion language pair. Common labels have draft translations for eleven languages, with pt-PT and zh-TW variants. Additional English resources extract static UI text, common errors and notification labels; dynamic text, model-generated notices, accessibility text, complete translations, native-language review, RTL checks and end-to-end visual tests remain outstanding.

The cardless Base draft parses optional server time and trial fields, uses the server clock anchored to monotonic device time, displays the free period without requiring a payment method, and avoids selecting a store trial for Base. Bot mini keeps its separate store trial. A Bot verification-unavailable response suppresses purchase calls to avoid duplicate purchases. These behaviors need contract-fixture and real lifecycle tests against the not-yet-deployed backend.

A prior observed expired plan remained visible as active until refresh. The draft refreshes at expiry and treats failed or unavailable verification as unknown. Native lifecycle tests remain required.

Offline `:app:compileDebugKotlin` succeeded for the work in progress after deliberately excluding immersion asset staging and source-context verification. It is a Kotlin/resource diagnostic only; it does not qualify assets, an APK, or release readiness. The full source-context verification currently rejects tracked `upstream-source-provenance-20261116.json` as an unexpected file. Translations and right-to-left layout are unreviewed.
