package co.fallsoft.vipi

import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Rule
import org.junit.Test

class NativeHelpDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun settingsHelpOpensEachLocalVisualGuideAndReturns() {
        MainActivityJourneyFixture("native-help", { VipiModel(it) }).use { f ->
            compose.runOnIdle { f.model.navigate(Screen.SETTINGS) }
            f.launch()
            compose.onNodeWithTag("settings-help").performScrollTo().performClick()
            compose.onNodeWithTag("tutorial-reentry").assertIsDisplayed()
            compose.waitForIdle()
            SystemClock.sleep(350)
            f.capture("android-native-help")
            for (topic in listOf("FRIENDS", "GROUPS", "LANGUAGES", "READING", "VOICE", "STATUS", "NOTIFICATIONS", "SAFETY", "BACKUP", "ACCOUNT")) {
                val row = compose.onNodeWithTag("help-topic-$topic")
                row.performScrollTo().performClick()
                val detail = compose.onNodeWithTag("help-detail-$topic")
                detail.performScrollTo().assertIsDisplayed()
                if (topic == "FRIENDS") {
                    compose.waitForIdle()
                    SystemClock.sleep(350)
                    f.capture("android-native-help-friends")
                }
                row.performScrollTo().performClick()
                detail.assertDoesNotExist()
            }
            compose.onNodeWithContentDescription(f.base.getString(R.string.nav_back)).performScrollTo().performClick()
            compose.waitUntil { f.model.screen == Screen.SETTINGS }
        }
    }
}
