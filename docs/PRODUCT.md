# Vipi product

Vipi is free, end-to-end encrypted chat for people who want to practice
another language with friends or family. The phone translates and reads
messages aloud while the original chat stays available in the conversation.

## Launch scope

- Native iOS and Android clients with direct and group chats, quoted replies,
  link previews, emoji reactions and conversation streaks. Direct chats also
  support photo, video and voice messages. Public availability is recorded
  separately in the [release runbook](HUMAN_RELEASE.md).
- FallSoft sign-in, private email, usernames and invitation links. People can
  connect without uploading their address book. One primary phone per account
  has an explicit replacement flow and peer identity-change notices.
- On-device translation, transliteration and speech. Translation downloads can
  be prepared and retried while ordinary chat remains usable. Check the
  [language inventory](LOCAL_LANGUAGE_SUPPORT.md) for device support and speech
  qualification.
- System, light and dark appearance. Review compact widths, large type, keyboard
  and safe-area behavior, screen readers, reduced motion and right-to-left text
  before releasing a UI change.

## First experience

1. Show how a message reads in practice language, how to listen and how to
   reveal the original.
2. Ask which language the person knows and which language they want to
   practice. Explain any model download and let them continue to chat.
3. Use FallSoft sign-in, set a username and present the terms and privacy
   information.
4. Open the inbox with a clear way to invite a friend. Request optional
   notifications when their benefit is clear. Preserve progress across
   cancellation, backgrounding and a failed download.

## Conversation

The Immersion control offers two modes. Shallow introduces at most one new
word per eligible message and repeats terms the person has already seen.
Deep translates the complete message. Both modes preserve the original.
Switching modes keeps the conversation and draft open. The practice language
can be changed from the conversation header. [Immersion behavior](INCREMENTAL_IMMERSION.md)

Tap to hear the practice language with word highlighting. Hold to see the
original and double-tap to switch script where a reading is available. Autoplay
is optional and stops when turned off or when the conversation is left.
Keep the reading position stable through these changes. Provide distinct UI
for a missing model, a retryable failure and an undelivered message.

## Free accounts and privacy

Ordinary chat is free and base access does not expire. Existing purchase
rights, history and account references remain recoverable. Older paid flows
remain documented in the [store reconciliation guide](STORE_RECONCILIATION.md).

The relay holds encrypted envelopes pending delivery, using a 72-hour
deadline from the original send. A retry retains that deadline. Delivered
history lives on the devices and users can export an encrypted backup.

Vipi profile deletion is scoped to Vipi. The shared FallSoft account has
its own lifecycle. Reporting must explain exactly what a person chooses
to share. The service sends no message body in ordinary push hints. Review
metadata retention, backup scope, identity processing and current company
policies before publishing a privacy claim. [Human release checklist](HUMAN_RELEASE.md#distribute-review-and-publish)
