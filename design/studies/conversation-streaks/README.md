# Conversation streaks

The two curling waves mark consecutive UTC days of conversation. Both use one solid fill and an open curl that stays visible in an 18-unit drawing. The larger crest leads the smaller. The same two paths are preserved in [the iOS template asset](../../../ios/Vipi/Assets.xcassets/FriendStreakWave.imageset/friend-streak-wave.svg) and [the Android vector drawable](../../../android/app/src/main/res/drawable/vipi_friend_streak_wave.xml).

In a list row the mark sits with the conversation name. The timestamp keeps the trailing edge and unread messages retain their filled circle. The exact localized day count uses tabular figures without a capsule. The count appears from two days. Tapping the conversation header count explains whose messages qualify. Direct chats count days with a delivered message in each direction. Groups count days when at least two distinct members participate.

| Client | Wave | Gap to digits | Digits |
| --- | --- | --- | --- |
| iOS | 18 pt at default size, scaling to 24 pt | 3 pt | Bold SF subheadline with monospaced digits, ink |
| Android | 20 dp | 3 dp | Bold Material titleSmall with tabular digits, onSurface |

The wave uses the action accent. The reference light canvas gives the wave a 7.33:1 contrast ratio and the count 13.95:1. The dark canvas gives 8.99:1 and 14.54:1 respectively. The day count remains legible when its accent color is unavailable.

The count studies use the original vector, native system SF and the regular Android emulator’s variable Roboto. They place 2, 7, 30 and 1,024 beside invented chat names on each platform’s light and dark canvases. Native app captures are identified separately on the review page. [Count studies and native review](https://system76-pc.tailb77f2a.ts.net/8bar/vipi-studio-20261120/conversation-streaks-20261121-r01/conversation-streaks.html) · [Inspected reference screens and Built for Mars articles](../../mobbin/README.md#conversation-streaks-in-direct-and-group-chats)
