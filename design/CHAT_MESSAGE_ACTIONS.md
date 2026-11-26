# Replies, reactions and link previews

These are the last three launch features for direct chats and groups. Vipi keeps its own bubble, typography and color system. The selected message stays in place while the user acts on it.

## Quoted replies

Swipe a message toward the trailing edge to reply. Mirror the direction in right-to-left layouts. Horizontal intent must win before the gesture starts. Vertical scrolling and the press-and-hold translation gesture stay available. Include Reply in Message actions and as an accessibility action on the bubble.

Put a two-line quote above the composer with the author, a short snippet and a close button. Preserve the current draft and focus the same composer. The sent reply shows the quote just above its message text. Tapping the quote jumps to the original when it is in local history, with a brief highlight. If the original is unavailable, show the encrypted snippet and omit the jump. Use short media labels such as Photo or Voice message. Show the locally rendered quote when its original is available, so the quote follows the same Shallow or Deep setting as the conversation. The reply text stays the only part the main bubble tap speaks.

[WhatsApp quote in the composer on Mobbin](https://mobbin.com/screens/31575490-2af7-4af7-9b50-b4bc98576910)

## Emoji reactions

Use the message footer as a compact Message actions button. Keep delivery state and time visible and expose Reply and React through the platform accessibility menu. An opposite-direction swipe is a shortcut to the same menu. A short context hint can teach these actions without putting another toolbar above the composer.

Anchor the quick emoji row to the selected bubble. Offer a few frequent reactions and a More action for the full picker. One tap applies a reaction. Choosing another replaces it. Choosing the active one clears it. In the thread, keep a compact pill next to the bubble. Tapping the pill opens the list of who reacted, with the current user’s reaction easy to change. A reaction event never enters the new-message, streak, autoplay or full-text-translation flow.

[WhatsApp reaction tray on Mobbin](https://mobbin.com/screens/4ec6e62a-70da-4ba8-9105-3e9101684697) · [Signal reaction behavior](https://support.signal.org/hc/en-us/articles/360039929972-Message-Reactions)

## Link previews

For an eligible HTTPS URL in the draft, show **Add preview** near the composer. That action requests a preview from the destination on the sender’s device. Use a compact, removable card with title, actual domain and a small thumbnail when available. A slow or unavailable preview leaves the text immediately sendable. Editing or removing the URL cancels its pending preview.

The sender encrypts the preview with the message. The recipient renders the embedded snapshot and contacts the website only after tapping to open it. Show the domain derived from the actual URL in the preview card. Open the link in the system browser. The card should share width and contrast with its bubble, with no animation that moves other messages while history loads.

[WhatsApp dismissible preview on Mobbin](https://mobbin.com/screens/50cfe56b-b253-41cc-8034-ec66fecf1154) · [Signal link preview settings](https://support.signal.org/hc/en-us/articles/360022474332-Link-Previews) · [Built for Mars Signal privacy teardown](https://builtformars.com/case-studies/creating-a-signal-account)

## Gesture and accessibility checks

Tap the bubble body to listen. Hold to show the original, and release to restore immersion. Double-tap retains the script toggle. For horizontal actions, show a small directional affordance after intent is clear and provide a single haptic at the action boundary. A diagonal scroll, a hold, a double-tap and a partially completed swipe must leave the composer and the message unchanged. VoiceOver and TalkBack can open both actions directly. Check large text, right-to-left layouts and a long message near the keyboard. Each surface uses the existing system dismissal behavior.

The Built for Mars review recommends contextual actions, a dismissible quote and sender-side preview consent. Applying that here means keeping the preview as a composer choice and using the footer for message actions, so the existing immersion hold remains predictable. [Built for Mars on accumulated interface friction](https://builtformars.com/case-studies/gmail)

## Wire and local state

- Add a single optional versioned metadata object inside the existing authenticated direct and group plaintext. A reply points to an original sender and message ID, with a bounded snippet and optional media label. Direct replies use the direct message UUID. Group replies use the shared logical group message UUID. Resolve a referenced row only in the same conversation and verify its recorded sender. Unknown metadata versions leave the ordinary message text available.
- Link metadata contains the exact composed URL, bounded text, and optionally a small safe thumbnail embedded as bytes. Generate and validate the displayed host from the URL. Verify it occurs in the message, limit the encoded payload below the current ciphertext cap, and permit sending the bare link whenever that validation or fetch fails. Reject credentials, local destinations and unsafe redirects. Use an ephemeral HTTP client without cookies or script execution. Include the sender-side request in the privacy disclosure.
- Model a reaction as an authenticated participant’s set or clear of one emoji on an existing message. Apply idempotently with a stable event ID and per-sender ordering. Retain the last clear so older deliveries cannot restore a removed reaction. Bound unresolved targets and reconcile them when the original arrives. In groups, validate the current authenticated roster before recording the update. Apply it inside the same vault transaction as decryption and deduplication.
- Advertise reaction support through the active device’s capabilities. Only send reactions when the target device supports the event, including every active recipient of a group reaction. Refresh on device changes. Older clients can still read ordinary text with optional reply or preview metadata. Never rely on older clients to swallow an empty-body event. The relay needs only the capability integer and ciphertext, with no message target, emoji, link or quoted text in its metadata.

Use the same keys on both clients. The following object can accompany ordinary message text.

```json
{
  "chat_features": {
    "version": 1,
    "reply": {
      "message_id": "a3c5b7b1-cc3e-4f0f-9fdb-66202213e0ef",
      "sender_id": "9d65b045-0e8c-489b-a634-4005e8dbcf2a",
      "kind": "text",
      "excerpt": "See you at noon."
    },
    "link_preview": {
      "url": "https://example.com/",
      "title": "Example site"
    }
  }
}
```

An event uses the same object with `reaction` alone and the encrypted body `Reaction`. Its fields are `message_id`, `target_sender_id`, `sequence` and `emoji`. The enclosing message authenticates the actor and the event ID. A null emoji clears that actor’s reaction. Scope the positive sequence to the conversation, actor, active sender device and target message. Confirm the device with the existing Signal route. Delayed entries from a replaced device may not overwrite new entries. A reaction lacking the required permission or a recognized payload cannot update local state.

Publish support as `PUT /v1/devices/chat-features` with `{"version":1}`. A sender checks the direct peer’s active device through `GET /v1/people/{id}/chat-features` or checks each member’s `chat_features_version` on the group roster. Set `required_chat_features_version:1` on reaction admissions. Clients that understand reactions opt into receiving them with `X-Vipi-Chat-Features: 1` on the existing inbox route. Older clients see the text of other messages and never see a reaction placeholder. The relay withholds reaction alerts from OS notifications and leaves ciphertext on its ordinary authenticated delivery route.

Use a maximum of 512 UTF-8 bytes for the quote, 2,048 for the URL, 512 for the title and 8 KiB for an optional encoded image’s decoded bytes. Check the envelope size after encryption. When it would exceed the existing limit, send the draft without its preview image, then without the card if needed. Display and send the quoted caption or original text through the existing encrypted history store. Existing exports restore the text they already cover.

## Acceptance

Extend the maintained two-platform integration journey with one conversation that sends a quote and removable link snapshot, adds and clears a reaction, then repeats the relevant cases in a group. Confirm both clients use the same logical target and survive duplicate and out-of-order delivery. Check that the excluded group member receives no update, the recipient makes zero preview requests, and the old-client text and reaction capability behavior remain correct. Keep the separate handset checks for haptics, accessibility gestures and system-browser handoff.

Run [the native journey](../scripts/test-native-chat-actions.py) with the same source revision built for both platforms, dedicated clean simulators and a backend Python environment with Vipi’s dependencies. It starts a loopback relay with synthetic sign-in, drives the native test selectors and retains one receipt per stage. It also audits that the relay admitted the final group reaction only for the remaining member. The preview fixture returns a known sender-side title, and notification tests pass the encrypted ticket through the real client vault. Hosted sign-in and OS push delivery use their separate device checks.
