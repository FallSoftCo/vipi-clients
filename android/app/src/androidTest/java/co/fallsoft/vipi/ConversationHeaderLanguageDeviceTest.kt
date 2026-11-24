package co.fallsoft.vipi

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.util.UUID

class ConversationHeaderLanguageDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun compactControlsStayOnTheConversationRowAtStandardWidth() {
        val peer = UUID.randomUUID()
        var width by mutableStateOf(280.dp)
        var fontScale by mutableStateOf(2f)
        compose.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, fontScale)) {
                VipiTheme(Appearance.LIGHT) {
                    Surface(Modifier.fillMaxSize()) {
                        ConversationHeader("A long conversation name", peer, false, true, {},
                            ImmersionMode.NEW_WORD, {}, 48.dp, Modifier.width(width).testTag("conversation-header"),
                            languageSource = "en", languageTarget = "es", languageDefaultTarget = "fr",
                            languageUsesDefault = false, onLanguage = {}, onUseDefaultLanguage = {},
                            back = { IconButton({}) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, null) } },
                            overflow = { IconButton({}) { Icon(Icons.Outlined.MoreVert, null) } })
                    }
                }
            }
        }
        compose.runOnIdle { width = 360.dp; fontScale = 1f }
        compose.waitForIdle()
        val header = compose.onNodeWithTag("conversation-header").fetchSemanticsNode().boundsInWindow
        val contact = compose.onNodeWithTag("conversation-contact").fetchSemanticsNode().boundsInWindow
        val controls = listOf("conversation-language", "conversation-autoplay", "conversation-immersion").map { tag ->
            compose.onNodeWithTag(tag).assertIsDisplayed().assertWidthIsAtLeast(48.dp).assertHeightIsAtLeast(48.dp)
                .fetchSemanticsNode().boundsInWindow
        }
        controls.forEach { control ->
            assertTrue("control starts inside the header", control.left >= header.left)
            assertTrue("control ends inside the header", control.right <= header.right)
            assertEquals("compact controls share the conversation row", contact.center.y, control.center.y, 2f)
        }
        val ordered = controls.sortedBy { it.left }
        ordered.zipWithNext().forEach { (left, right) -> assertTrue("controls do not overlap", left.right <= right.left + 1f) }
        compose.onNodeWithTag("conversation-language-label", useUnmergedTree = true).assertTextEquals("ES")
        compose.onNodeWithTag("conversation-autoplay-label", useUnmergedTree = true).assertDoesNotExist()
        compose.onNodeWithTag("conversation-immersion-label", useUnmergedTree = true).assertDoesNotExist()
    }

    @Test fun allThreeControlsFitAtTwoHundredEightyDpAndDoubleText() {
        val peer = UUID.randomUUID()
        compose.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 2f)) {
                VipiTheme(Appearance.LIGHT) {
                    Surface(Modifier.fillMaxSize()) {
                        Box(Modifier.fillMaxSize()) {
                            ConversationHeader("A long conversation name", peer, false, true, {},
                                ImmersionMode.NEW_WORD, {}, 48.dp,
                                Modifier.width(280.dp).testTag("conversation-header"),
                                languageSource = "en", languageTarget = "es", languageDefaultTarget = "fr",
                                languageUsesDefault = false, onLanguage = {}, onUseDefaultLanguage = {},
                                back = { IconButton({}) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, null) } },
                                overflow = { IconButton({}) { Icon(Icons.Outlined.MoreVert, null) } })
                        }
                    }
                }
            }
        }
        val header = compose.onNodeWithTag("conversation-header").fetchSemanticsNode().boundsInWindow
        for (tag in listOf("conversation-language", "conversation-autoplay", "conversation-immersion")) {
            val control = compose.onNodeWithTag(tag).assertIsDisplayed()
                .assertWidthIsAtLeast(48.dp).assertHeightIsAtLeast(48.dp).fetchSemanticsNode().boundsInWindow
            assertTrue("$tag starts inside the header", control.left >= header.left)
            assertTrue("$tag ends inside the header", control.right <= header.right)
        }
        compose.onNodeWithTag("conversation-language-label", useUnmergedTree = true).assertTextEquals("ES")
        compose.onNodeWithTag("conversation-language").performClick()
        compose.onNodeWithTag("conversation-language-fr").assertExists()
        compose.onNodeWithTag("conversation-language-default").assertExists()
    }
}
