# Android localization and cardless access — native QA candidate

The qualified branch `0065768` was merged into delivery as `72700c6`. The committed Android tree is identical to the reviewed branch. The installed full-asset QA app was built from `9ea3fc7`; subsequent commits change instrumentation only. The previously uploaded Android release is unchanged.

Interface localization follows Android's app locale independently of the immersion pair. Twelve non-English locale catalogs include Portuguese and Chinese variants. Context review corrected ambiguous action/error translations and the remaining extracted dynamic/accessibility labels. This is not comprehensive native-speaker acceptance or a claim that every screen has been exercised in every locale.

Base access uses server time anchored to monotonic device time, displays the account-bound free period without a payment method, and avoids choosing a store introductory offer for Base. Bot mini retains its separate store trial. Unknown verification withholds purchase actions. Profile creation and same-account return route to Chats instead of forcing Plans. The cardless backend is now deployed in restricted staging; the native checks below use controlled offline fixtures and do not establish a new customer or store lifecycle.

A previously observed paid-plan expiry stayed active until refresh. The current candidate refreshes at expiry and presents failed verification as unknown. Active, unknown and confirmed-expired cardless fixture presentations were reviewed. Existing real Google license purchase/renewal/cancellation evidence belongs to the older uploaded release and must not be replayed or represented as qualification of this revised flow.

Full pinned-asset QA build and installation passed. App SHA-256: `a436189fcf9d8e6c893a992883b34e1c99b8c2340a5e7205b97b3250ab8e9952`. Current instrumentation SHA-256: `722839332ff0479873c0720978cae0faac36af17d7f85cc5e77ec7efb3cee3ac`. The earlier asset-check failure was resolved before this full build; no asset-staging bypass is claimed as release evidence.

Observed checks include:

- Profile routing and optional-leading-`@` lookup with fake transports.
- Native Stop, unchanged inline text width, real TalkBack pause/manual controls, and Spanish repeated-word/overflow actions.
- Disabled recovery new-chat control, including a tap that does not navigate.
- Separate backup Save/Restore modes, no confirmation field for Restore, native picker opening and safe cancellation without choosing or changing a file.
- Populated production chat with synthetic local messages in light mode and dark mode at 1.5× text, readable metadata and composer above the keyboard.
- Arabic changed-key dialog: current and candidate numbers each have 60 digits whose visible semantic text matches the digit-wise accessibility description; cancellation leaves them unconfirmed. This is not a claim of spoken Arabic TalkBack output.

Private evidence is under `investigations/vipi-android-localization-20261117-r01/resource-validation/`: `full-candidate-9ea3-build-receipt.json`, `qa-9ab-offline-flow.log`, `qa-b216-chat-{light,darklarge}.log`, `qa-0065-arabic-number.log`, and the corresponding screenshot directories. Root independently reviewed the relevant native captures. No real peer message, purchase, account creation, or store submission was part of these checks.

Remaining release work includes broader localized accessibility review, the actual post-migration account flow, removal of the old Base store offer, and qualification of the final store artifact. The current QA result does not certify “world class,” linguistic accuracy across all messages, or store readiness.
