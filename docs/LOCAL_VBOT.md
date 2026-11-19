> Superseded November 19, 2026: the owner removed vBot from Vipi. This document records historical investigation only. See INCREMENTAL_IMMERSION.md for current scope.

# Local vBot

Implementation in progress, November 19, 2026. Not deployed or release accepted.

vBot generation moves to the operating system's onboard model, with no separate Bot mini purchase. The base Vipi subscription and cardless first month are unchanged. Existing store subscriptions are not automatically cancelled by this code change; retain a management link for historic Bot mini customers.

## Platform findings

Apple's Foundation Models framework exposes the Apple Intelligence model on eligible devices with iOS 26 or later. Availability must be checked on the actual device; enabled Apple Intelligence, model preparation, region and language all matter. This is not a public Siri chat API. [Apple's generation guide](https://developer.apple.com/documentation/foundationmodels/generating-content-and-performing-tasks-with-foundation-models) and [language guidance](https://developer.apple.com/documentation/foundationmodels/supporting-languages-and-locales-with-foundation-models) describe those requirements. The installed Xcode 26.5 interface is authoritative for this build; newer web documentation has renamed some error APIs.

The retained native Mac manually exercised a two-turn conversation on November 19. The first response took about 10.2 seconds and the second 3.8 seconds. Both were coherent but generic; this establishes API feasibility on that Mac, not mobile quality acceptance. The model listed 15 base languages. Arabic and Swahili were absent; translation support and generation support are independent.

[Google's direct Gemini Nano API](https://developers.google.com/ml-kit/genai/prompt/android) supports client-managed conversations. The current dependency is beta; device availability, preparation, foreground execution and resource limits must be handled. An eligible device model name is not proof that its model is ready. Do not silently send messages to a cloud provider when local generation is unavailable.

## Selected-reply reports

`POST /v1/bot/local-reports` is a new authenticated, registered-device endpoint. It does not generate a response or require a paid Bot plan. The request is sent only after the person confirms the selected reply and reason:

```json
{
  "report_id": "a stable UUID for this report and exact retry",
  "provider": "gemini-nano",
  "reason": "inaccurate",
  "selected_reply": "The reply shown in the confirmation screen",
  "consent_version": "local-bot-report-v1"
}
```

Provider is `gemini-nano` or `apple-foundation-models`. Reason is `harmful`, `inaccurate` or `other`. Selected text must be nonblank and at most 4000 UTF-8bytes. No transcript, friend message or hidden context is included. An exact retry returns 202 and `{"reported":true,"report_id":"…"}`. Reusing an ID for different content or an owner returns 409. Limit: 5 requests per minute per identity and 20 retained new reports per day per account. A failed request must not appear as successfully reported.

Reports use a separate table with no cloud reservation dependency. The selected payload is encrypted using a dedicated key derivation, deleted after 30 days or account deletion, excluded from restored report content, and accessible only through the private moderator CLI as kind `local-bot`. Stored provider and text are user submissions, not verified model authorship. The old cloud report endpoint remains for historic cloud replies.

Migration `20261119_01` and its matching API must be deployed together after review. The new table must also be included in report-content exclusions in the production backup configuration before deployment. Nothing in this source change authorizes a production restart or schema update.
