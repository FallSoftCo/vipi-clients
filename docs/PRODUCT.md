# Product agreement

## Purpose

Vipi is second-language acquisition through immersion in personally relevant conversation. It is not a course, a vocabulary quiz, a lesson feed, or a grammar curriculum. The user chats with friends or vBot. Familiar context makes unfamiliar language understandable; the app lets the user reveal meaning without leaving the conversation.

## Launch scope

- Native iOS and Android, text input, one-to-one messaging. Data identifiers and message envelopes permit future groups and media without presenting unfinished controls.
- One active phone per account. Explicit phone replacement, identity-change notices, and user-controlled encrypted backup/restore.
- WorkOS identity. Email is private account information; usernames and invitation links connect friends without mandatory address-book upload or SMS.
- Human chats use end-to-end encryption. vBot is a distinct service conversation, disclosed before the first prompt leaves the device.
- Local full-message translation, live transliteration and local text-to-speech. Model downloads expose preparation, retry and removal controls. Network translation is not a fallback.
- Server delivery expires 72 hours after the original send. Retries do not extend it. Delivered history stays on the phones; an expired undelivered message is visibly different from a delivered message.
- Themes: system, light, dark. Accessible text scaling, screen readers, reduced motion, keyboard handling, safe areas, back navigation, and RTL must work.

## First experience

1. A concise explanation: “Chat with friends. Learn a language.” A real local-translation preview demonstrates tap to listen, hold to see meanings and double-tap to change script. It is clearly a preview, not a fake conversation.
2. Confirm the language the user knows and choose an immersion language from actually supported local translation directions. Explain downloads and let chat remain usable while they prepare.
3. Create/sign into an account, pick a unique username, and accept FallSoft.Co terms and Vipi product disclosures.
4. Provide 30 days of Base access from original profile creation without payment details. Show the actual end date. Signing in enrolls neither subscription and expiry creates no charge; continued paid access requires an explicit store purchase.
5. Land in the real chat list with clear choices to invite a friend or talk to vBot. The optional Bot mini offer appears when the user chooses vBot; base onboarding does not enroll the add-on.
6. Request notifications when their benefit is clear, with a graceful denial path. Never gate first use on address-book access.

Do not overload onboarding with tutorials, carousels, notification prompts, downloads, and purchase dialogs simultaneously. Preserve progress through cancellation, backgrounding, relaunch, and failed download.

## Conversation

Every sent or received message appears fully translated into the practice language. Non-Latin practice text shows live transliteration by default, including Chinese tone marks. There is one message surface, without stacked translations or automatically flipping words.

Tap a message to hear its complete practice-language audio. Hold the chat area to reveal native-language meanings for all visible messages; release restores the practice display. Double-tap toggles practice script and transliteration without playing audio. A speaker toggle in the header enables automatic playback of new messages, off by default. Leaving the chat, backgrounding or turning it off stops pending and active playback.

The authored original stays unchanged in encrypted storage and remains available through copy-original. Translation preparation and failure are explicit and retryable. Rendering must preserve the reading position across reveal/script changes and respect native text scaling, RTL, editable controls and screen-reader actions. The complete current behavior and qualification requirements are in [Full-message immersion](FULL_MESSAGE_IMMERSION.md).

## Plans

| Plan | Annual target price (USD) | Trial | Scope |
|---|---:|---|---|
| Vipi | $12 | 30 days without payment details, from profile creation | Friends, local immersion, speech, encrypted backup tools |
| Bot mini | $48 additional | One month, store eligibility applies | vBot responses, with a disclosed monthly allowance |

Only these two plans launch. Storefront localized prices and billing periods are authoritative. Confirm supported exact price points during store configuration. Bot mini depends on a Vipi entitlement; handle base cancellation, lapse, refund, and recovery without leaving an unusable paid add-on unexplained. Purchase design must show total recurring commitments, restore purchases, and management links. A lapsed subscription must not prevent users reading/exporting their existing local history or deleting their account.

Bot mini's provisional provider-spend ceiling is $0.50 per account per month, including its trial. This is an engineering budget, not customer-facing currency credit. Establish a useful and comprehensible message allowance through measured workloads. No unlimited promise, automatic overage, rollover, or larger plans at launch.

## Privacy and company policies

Company: Fallible Software, Co. Product terms supplement https://fallsoft.co/terms-of-service and https://fallsoft.co/privacy-policy. Source policy text inspected in the company repository is dated July 23, 2026; verify deployed text before publishing.

Follow stated purposes and data minimization; no advertising/tracking SDKs or sale of personal data. Account deletion and data export must be functional. Product disclosures must explain retained metadata, 72-hour ciphertext delivery, device storage, encrypted backups, OS model downloads, subscription processors, WorkOS, and DeepSeek processing for vBot. Never imply the bot has the human-chat E2EE boundary. Review/reporting and block flows must meet current store requirements without silently forwarding private chats; a user-selected report must explain precisely what is shared.

Marketing may describe tested properties. “Perfect security,” “zero metadata,” “guaranteed delivery,” “80 supported languages,” or WhatsApp-equivalent performance cannot be claimed without matching evidence. One million paying users is a scale target, not a measured launch capacity.
