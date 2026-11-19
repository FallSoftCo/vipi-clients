# Free, incremental Vipi

Owner decision, November 19, 2026. This replaces the full-message immersion,
vBot, subscription and one-month trial plans. Earlier evidence remains historical.

Vipi is free chat with friends. There is no chatbot, payment, in-app purchase,
trial deadline or sending entitlement. End-to-end encrypted friend messaging,
invites, local history, backups and account deletion remain.

Each new message introduces one previously unseen source word when its text
contains one that can be translated. Words already introduced also appear in the
practice language when they occur again. The surrounding wording stays intact.
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

Target words have live transliteration by default where required. Source text
must never be transliterated as though it were in the target language. Tapping
plays the practice words using their original target script and target voice;
holding reveals the original wording, and double tapping switches the reading
and native script. Inline word backgrounds use the existing stable sizing.

Language/TTS/transliteration support is accepted by direct manual review and
documented platform evidence in LOCAL_LANGUAGE_SUPPORT.md, not by test counts.
Automated checks cover progression, persistence, cancellation, isolation and
messaging behavior. New builds remain on the existing release hold until the
actual two-platform experience is reviewed. No store or production action is
implied by this source revision.
