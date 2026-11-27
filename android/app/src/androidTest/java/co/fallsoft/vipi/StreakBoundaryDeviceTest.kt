package co.fallsoft.vipi

import android.content.res.Configuration
import android.os.LocaleList
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.unit.*
import androidx.test.platform.app.InstrumentationRegistry
import java.util.Locale
import java.util.UUID
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class StreakBoundaryDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun foregroundMidnightExpiresYesterdayWithoutAnotherMessageOrNavigation() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val vault = MessageVault(ctx, account)
        val day = 20_000L
        try {
            vault.transaction {
                for (qualifying in listOf(day - 2, day - 1)) for (out in listOf(true, false)) {
                    ConversationStreaks.direct(
                        vault,
                        peer,
                        out,
                        qualifying * ConversationStreaks.DAY_MS,
                    )
                }
            }
            val started = SystemClock.elapsedRealtime()
            val clock = {
                (day + 1) * ConversationStreaks.DAY_MS - 6_000L + SystemClock.elapsedRealtime() -
                    started
            }
            compose.setContent {
                CompositionLocalProvider(LocalStreakClock provides clock) {
                    val count = streakCounts(vault, false, listOf(peer), 0)[peer]
                    Text("active=${count ?: -1}")
                    ChatStreakBadge(count ?: 0)
                }
            }
            compose.waitUntil(5_500) {
                compose.onAllNodesWithText("active=2").fetchSemanticsNodes().isNotEmpty()
            }
            compose.onNodeWithTag("chat-streak").assertIsDisplayed()
            compose.waitUntil(12_000) {
                compose.onAllNodesWithText("active=0").fetchSemanticsNodes().isNotEmpty()
            }
            compose.onNodeWithTag("chat-streak").assertDoesNotExist()
        } finally {
            vault.close()
        }
    }

    @Test
    fun unreadableOriginalPageLeavesChatUsableAndCanResumeAfterRepair() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val vault = MessageVault(ctx, account)
        var revision by mutableIntStateOf(0)
        val corruptID = UUID.randomUUID()
        val day = System.currentTimeMillis() / ConversationStreaks.DAY_MS
        try {
            vault.transaction {
                for (d in day - 1..day) for (out in listOf(true, false)) ConversationStreaks.direct(
                    vault,
                    peer,
                    out,
                    d * ConversationStreaks.DAY_MS,
                )
                vault.put("outgoing", corruptID.toString(), "unreadable".toByteArray())
            }
            compose.setContent {
                // The actual screens call the same index reader. A new visit
                // should retry, but repeated recomposition must never spin.
                val counts = key(revision) { streakCounts(vault, false, listOf(peer), 0) }
                Button(onClick = { revision++ }) { Text("Open conversation") }
                ChatStreakBadge(counts[peer] ?: 0)
            }
            compose.onNodeWithText("Open conversation").assertIsDisplayed()
            compose.waitUntil(4_000) {
                vault.transaction {
                    vault.get("metadata", "streak-backfill-incoming") != null &&
                        vault.get("metadata", "streak-backfill-outgoing") == null
                }
            }
            compose.onNodeWithTag("chat-streak").assertDoesNotExist()
            val e =
                ChatEnvelope(
                    corruptID,
                    account,
                    peer,
                    day * ConversationStreaks.DAY_MS,
                    2,
                    ByteArray(32),
                )
            vault.transaction {
                assertEquals(
                    "unreadable",
                    vault.get("outgoing", corruptID.toString())!!.toString(Charsets.UTF_8),
                )
                vault.put(
                    "outgoing",
                    corruptID.toString(),
                    StoredChat(e, "Hello", "delivered").encode(),
                )
            }
            compose.onNodeWithText("Open conversation").performClick()
            compose.waitUntil(8_000) {
                compose.onAllNodesWithTag("chat-streak").fetchSemanticsNodes().isNotEmpty()
            }
        } finally {
            vault.close()
        }
    }

    @Test
    fun largeRtlFourDigitHeaderKeepsCompleteNumeralAndTapTarget() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val peer = UUID.randomUUID()
        val arabic = Locale.forLanguageTag("ar")
        val expected = java.text.NumberFormat.getIntegerInstance(arabic).format(1024)
        val config =
            Configuration(ctx.resources.configuration).apply { setLocales(LocaleList(arabic)) }
        val count =
            MessageVault(ctx, UUID.randomUUID()).use { vault ->
                val today = System.currentTimeMillis() / ConversationStreaks.DAY_MS
                vault.transaction {
                    for (day in today - 1023..today) for (out in
                        listOf(true, false)) ConversationStreaks.direct(
                        vault,
                        peer,
                        out,
                        day * ConversationStreaks.DAY_MS,
                    )
                    ConversationStreaks.count(vault, false, peer, today)
                }
            }
        assertEquals(1024, count)
        compose.setContent {
            CompositionLocalProvider(
                LocalLayoutDirection provides LayoutDirection.Rtl,
                LocalConfiguration provides config,
                LocalDensity provides Density(LocalDensity.current.density, 2f),
            ) {
                VipiTheme(Appearance.DARK) {
                    Surface(Modifier.fillMaxSize()) {
                        Box(Modifier.fillMaxSize().statusBarsPadding()) {
                            ConversationHeader(
                                "مريم",
                                peer,
                                false,
                                true,
                                {},
                                ImmersionMode.NEW_WORD,
                                {},
                                48.dp,
                                Modifier.width(280.dp),
                                streak = count,
                                back = {
                                    IconButton({}) {
                                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, null)
                                    }
                                },
                                overflow = {
                                    IconButton({}) { Icon(Icons.Outlined.MoreVert, null) }
                                },
                            )
                        }
                    }
                }
            }
        }
        val badge = compose.onNodeWithTag("chat-streak", true)
        badge.assertIsDisplayed().assertWidthIsAtLeast(48.dp).assertHeightIsAtLeast(48.dp)
        val bounds = badge.fetchSemanticsNode().boundsInWindow
        val texts =
            compose
                .onAllNodes(hasAnyAncestor(hasTestTag("chat-streak")), true)
                .fetchSemanticsNodes()
        assertTrue(
            texts.all {
                val b = it.boundsInWindow
                b.left >= bounds.left && b.right <= bounds.right
            }
        )
        val label =
            badge
                .fetchSemanticsNode()
                .config[androidx.compose.ui.semantics.SemanticsProperties.ContentDescription]
                .single()
        assertTrue(label.contains(expected))
        val args = InstrumentationRegistry.getArguments()
        if (args.getString("vipiDedicatedEmulator") == "true") {
            val inst = InstrumentationRegistry.getInstrumentation()
            val output =
                java.io.File(ctx.filesDir, "streak-header-${args.getString("vipiJourneyRun")}.png")
            check(!output.exists())
            SystemClock.sleep(300)
            check(androidx.test.uiautomator.UiDevice.getInstance(inst).takeScreenshot(output))
        }
        badge.performClick()
        compose.onNode(isDialog()).assertExists()
    }
}
