package co.fallsoft.vipi

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/** Onboarding and conversations must share one message-row geometry. */
class ConversationMessageRowDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun shortMessageHugsContentWithProductionGutterAndMetadata() {
        compose.setContent {
            VipiTheme(Appearance.LIGHT) {
                Surface(Modifier.width(400.dp)) {
                    ConversationMessageRow(
                        outgoing = true,
                        modifier = Modifier.testTag("row"),
                        bubbleModifier = Modifier.testTag("bubble"),
                    ) {
                        Column(Modifier.padding(horizontal = 15.dp, vertical = 12.dp)) {
                            Text("Coffee tomorrow?")
                            Spacer(Modifier.height(6.dp))
                            ChatMessageMetadata(
                                "accepted",
                                1_700_000_000_000L,
                                true,
                                Locale.US,
                                "message-meta",
                            )
                        }
                    }
                }
            }
        }

        val row = compose.onNodeWithTag("row").fetchSemanticsNode().boundsInWindow
        val bubble = compose.onNodeWithTag("bubble").fetchSemanticsNode().boundsInWindow
        val density =
            InstrumentationRegistry.getInstrumentation()
                .targetContext
                .resources
                .displayMetrics
                .density
        assertTrue(
            "Short content must not stretch to the available width",
            bubble.width < row.width - 32.dp.value * density,
        )
        assertEquals(
            "Outgoing bubbles keep the production trailing edge",
            row.right,
            bubble.right,
            1f,
        )
        compose.onNodeWithTag("message-meta").assertExists()
    }
}
