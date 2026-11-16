# Android local translation feasibility: model availability

The shared 18-case synthetic fixture was tested on emulator-5620 with Wi-Fi and mobile data disabled. All 18 cases lacked at least one required non-English ML Kit model. No translations, latency measurements, or alignment results were produced, and no model download was invoked. Network settings were restored and protected application files remained byte-identical. English is treated as ML Kit's built-in language, matching the application's existing model-readiness logic.

The instrumented test is ready to compare full messages, selected phrases, and progressively expanded windows if the exact models are already installed in a later authorized environment. A literal occurrence count is recorded only as a diagnostic, not as proof of word alignment or meaning. This does not enable automatic translation.
