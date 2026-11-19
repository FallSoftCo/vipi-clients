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
                compose.onNodeWithText(f.base.getString(R.string.backup_password_too_short)).assertExists()
                compose.onNodeWithTag("backup-password").performTextReplacement("a".repeat(1025))
                compose.onNodeWithTag("backup-create").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-password").assertIsFocused()
                value("backup-password", "a".repeat(1025))
                compose.onNodeWithText(f.base.getString(R.string.backup_password_too_long)).assertExists()
                val passphrase = "An owned backup passphrase"
                compose.onNodeWithTag("backup-password").performTextReplacement(passphrase)
                compose.onNodeWithTag("backup-confirmation").performTextReplacement("A different passphrase")
                compose.onNodeWithText(f.base.getString(R.string.backup_password_mismatch)).assertDoesNotExist()
                compose.onNodeWithTag("backup-create").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-confirmation").assertIsFocused()
                value("backup-confirmation", "A different passphrase")
                value("backup-password", passphrase)
                compose.onNodeWithText(f.base.getString(R.string.backup_password_mismatch)).assertExists()
                f.capture("01-attempted-create-mismatch")
                compose.onNodeWithTag("backup-confirmation").performTextReplacement(passphrase)
                compose.onNodeWithText(f.base.getString(R.string.backup_password_mismatch)).assertDoesNotExist()
                compose.onNodeWithTag("backup-create").assertIsEnabled()
                f.device.pressBack()
                compose.onNodeWithText(f.base.getString(R.string.ui_beb6c51b9bf6)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("backup-password").performTextReplacement("")
                compose.onNodeWithTag("backup-open").performScrollTo().assertIsEnabled().performTouchInput { click() }
                compose.onNodeWithTag("backup-password").assertIsFocused()
                compose.onNodeWithText(f.base.getString(R.string.backup_password_too_short)).assertExists()
                assertEquals(Screen.BACKUP, f.model.screen)
                assertFalse(File(f.isolated.noBackupFilesDir, "history-transfer").walkTopDown().any { it.isFile })
                assertEquals(0,services.friendPosts.get()); assertEquals(0,services.botPosts.get())
                services.assertNoPurchase()
                f.capture("02-invalid-open-remains-in-backup")
            } finally { f.stopActivity(); services.close() }
        }
    }
}
