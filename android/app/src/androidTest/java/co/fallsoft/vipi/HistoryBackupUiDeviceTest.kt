package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual screen validation; no document picker, encrypted export or service send. */
class HistoryBackupUiDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    private fun value(tag: String, expected: String) = compose.onNodeWithTag(tag).assert(
        SemanticsMatcher.expectValue(SemanticsProperties.InputText, AnnotatedString(expected)))

    @Test fun attemptedBackupExplainsInvalidFieldsAndKeepsTheirValues() {
        val services = JourneyServices(profileRequired = false)
        MainActivityJourneyFixture("backup-validation", { services.model(it) }).use { f ->
            fun visibleFeedback(field:String, text:String) {
                compose.waitUntil(8_000) {
                    val keyboard = f.instrumentation.uiAutomation.windows
                        .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                        .map { android.graphics.Rect().also(it::getBoundsInScreen) }
                        .filter { it.height() > 0 && it.top in 1 until f.device.displayHeight }
                        .minOfOrNull { it.top } ?: return@waitUntil false
                    val top = compose.onNodeWithContentDescription(f.base.getString(R.string.nav_back)).fetchSemanticsNode().boundsInWindow.bottom
                    val input = compose.onNodeWithTag(field).fetchSemanticsNode().boundsInWindow
                    val error = compose.onNodeWithText(text).fetchSemanticsNode().boundsInWindow
                    input.height > 0 && error.height > 0 && input.top >= top && error.top >= top &&
                        input.bottom <= keyboard && error.bottom <= keyboard
                }
                compose.onNodeWithTag(field).assertIsFocused()
                compose.onNodeWithText(text).assertIsDisplayed()
            }
            try {
                f.launch()
                compose.waitUntil(15_000) { f.model.screen == Screen.HOME }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performTouchInput { click() }
                compose.onNodeWithText(f.base.getString(R.string.ui_24f13e3dc8e4)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-create").performScrollTo().assertIsEnabled()
                compose.onNodeWithText(f.base.getString(R.string.backup_password_too_short)).assertDoesNotExist()
                compose.onNodeWithTag("backup-create").performTouchInput { click() }
                compose.onNodeWithTag("backup-password").assertIsFocused()
                value("backup-password", "")
                visibleFeedback("backup-password",f.base.getString(R.string.backup_password_too_short))
                compose.onNodeWithTag("backup-password").performTextReplacement("a".repeat(1025))
                compose.onNodeWithTag("backup-create").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-password").assertIsFocused()
                value("backup-password", "a".repeat(1025))
                visibleFeedback("backup-password",f.base.getString(R.string.backup_password_too_long))
                val passphrase = "An owned backup passphrase"
                compose.onNodeWithTag("backup-password").performTextReplacement(passphrase)
                compose.onNodeWithTag("backup-confirmation").performTextReplacement("A different passphrase")
                compose.onNodeWithText(f.base.getString(R.string.backup_password_mismatch)).assertDoesNotExist()
                compose.onNodeWithTag("backup-create").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-confirmation").assertIsFocused()
                value("backup-confirmation", "A different passphrase")
                value("backup-password", passphrase)
                visibleFeedback("backup-confirmation",f.base.getString(R.string.backup_password_mismatch))
                f.capture("01-attempted-create-mismatch")
                compose.onNodeWithTag("backup-confirmation").performTextReplacement(passphrase)
                compose.onNodeWithText(f.base.getString(R.string.backup_password_mismatch)).assertDoesNotExist()
                compose.onNodeWithTag("backup-create").assertIsEnabled()
                f.device.pressBack()
                compose.onNodeWithText(f.base.getString(R.string.ui_beb6c51b9bf6)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-password").performTextReplacement("")
                compose.onNodeWithTag("backup-open").performScrollTo().assertIsEnabled().performTouchInput { click() }
                compose.onNodeWithTag("backup-password").assertIsFocused()
                visibleFeedback("backup-password",f.base.getString(R.string.backup_password_too_short))
                assertEquals(Screen.BACKUP, f.model.screen)
                assertFalse(File(f.isolated.noBackupFilesDir, "history-transfer").walkTopDown().any { it.isFile })
                assertEquals(0,services.friendPosts.get()); assertEquals(0,services.botPosts.get())
                services.assertNoPurchase()
                f.capture("02-invalid-open-remains-in-backup")
            } finally { f.stopActivity(); services.close() }
        }
    }
}
