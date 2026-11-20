package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/** Real settings + reopened model/preferences, controlled account/translation. */
class ImmersionSettingJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun reviewDefaultAndExplicitChoiceSurviveReopenWithoutChangingChatIdentityOrDraft() {
        check(BuildConfig.DEFAULT_FULL_IMMERSION) { "Run only the explicitly flagged full review build" }
        val services = JourneyServices(profileRequired = false)
        MainActivityJourneyFixture("immersion-mode-settings", services::model).use { f ->
            fun screen(value: Screen) = compose.waitUntil(15_000) { f.model.screen == value }
            fun openSettings() {
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performClick(); screen(Screen.SETTINGS)
                compose.onNodeWithText(f.base.getString(R.string.ui_e7cde359a05e)).performScrollTo().performClick(); screen(Screen.LANGUAGE_DOWNLOAD)
                compose.onNodeWithText(f.base.getString(R.string.immersion_mode_title)).assertIsDisplayed()
            }
            try {
                f.launch(); screen(Screen.HOME)
                assertEquals(ImmersionMode.FULL_MESSAGES, f.model.immersionMode)
                assertEquals(ImmersionMode.FULL_MESSAGES, f.model.chat?.translations?.mode)
                val draft = "Keep my unsent draft: café ☕."
                compose.runOnIdle { f.model.chat!!.saveCompose(draft, services.peer) }
                openSettings()
                compose.onNodeWithText(f.base.getString(R.string.immersion_mode_words)).performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.immersionMode == ImmersionMode.NEW_WORD && f.model.chat?.translations?.mode == ImmersionMode.NEW_WORD }
                f.capture("01-explicit-one-word")
                f.relaunch { app -> VipiModel(app, NoJourneyModelTranslation, services) }; screen(Screen.HOME)
                assertEquals(ImmersionMode.NEW_WORD, f.model.immersionMode)
                assertEquals(draft, f.model.chat?.compose(services.peer)); assertEquals(1, services.deviceRegistrations.get())
                openSettings()
                compose.onNodeWithText(f.base.getString(R.string.immersion_mode_full)).performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.immersionMode == ImmersionMode.FULL_MESSAGES && f.model.chat?.translations?.mode == ImmersionMode.FULL_MESSAGES }
                f.capture("02-explicit-full-message")
                f.relaunch { app -> VipiModel(app, NoJourneyModelTranslation, services) }; screen(Screen.HOME)
                assertEquals(ImmersionMode.FULL_MESSAGES, f.model.immersionMode)
                assertEquals(draft, f.model.chat?.compose(services.peer)); assertEquals(1, services.deviceRegistrations.get())
                assertEquals(services.account, f.model.chat?.profile?.id); services.assertNoPurchase()
            } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
            finally { f.stopActivity(); services.close() }
        }
    }
}
