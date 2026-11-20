# Free chat and immersion modes

Vipi is free, end-to-end encrypted chat with friends. In the conversation toolbar, **Immersion** opens a choice between **One new word at a time** and **Full messages**. Switching modes keeps the conversation and the draft open. Your choice applies when you open another chat.

In full-message mode, the phone translates each incoming and outgoing message into the practice language. A message already in that language keeps its original wording. Hold to see what the sender wrote. Viewing full translations leaves word-mode progress intact.

## One new word at a time

Each new message introduces one previously unseen source word when its text
contains one that can be translated. Words already introduced also appear in the
practice language when they occur again. The surrounding wording stays intact. The app varies the starting candidate using the message ID, so suitable unfamiliar words from anywhere in the message can be chosen. Encrypted message plans preserve each choice on rereading.
One hundred messages/words is an illustration, **not a cap** or a fluency claim.
There is no vocabulary completion threshold. Repeated words, emoji-only messages
and messages without a new translatable word do not manufacture progress.

The original message is immutable. Native word segmentation selects complete
source words, preserving punctuation, links and literal text. Translation uses
the existing on-device APIs; no phrase dictionary or generative model is needed.
Standalone word translations can choose the wrong sense of ambiguous words;
this simpler scope does not make them contextually guaranteed translations.

Progress belongs to the account and language direction, in encrypted local
storage. Keep individually indexed learned-word records and an immutable plan
for each message, with one atomic commit for a newly introduced word and that
message's presentation. Serialize new selections so simultaneous messages do
not introduce the same new word twice. Reopening, scrolling, retries, previews
and relaunches must not add more words to an already completed message.
Changing languages uses that pair's own progress. Memory caches may be bounded;
the learned vocabulary has no product cap. Onboarding examples do not count.

## Reading and playback

Target words have live transliteration by default where required. Source text
must never be transliterated as though it were in the target language. Tap a message to hear the practice language. The playing word is highlighted in the visible reading or script. Word mode inserts a brief pause when audio skips over intervening words. Full mode speaks the translated message continuously. Hold to see the original and double tap to switch between transliteration and script.

Language/TTS/transliteration support is accepted by direct manual review and
documented platform evidence in LOCAL_LANGUAGE_SUPPORT.md, not by test counts.
Automated checks cover progression, persistence, cancellation, isolation and
messaging behavior. New builds remain on the existing release hold until the
actual two-platform experience is reviewed. No store or production action is
implied by this source revision.

Completed messages retain an encrypted, immutable span plan separately from their disposable display cache. The plan and newly introduced word commit in one vault transaction. Clearing the cache or changing the reading policy rebuilds precisely those selected spans; it never selects another new word or inserts words learned later into old messages. Corrupt plans or missing vocabulary records produce a retryable failure rather than silent additional learning. Deleting a conversation removes its message plans while retaining the account’s learned vocabulary.
