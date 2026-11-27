package co.fallsoft.vipi

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.AdaptiveIconDrawable
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.content.res.ResourcesCompat
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/**
 * Current shipping root/navigation and native assets. No account sign-in, real messages,
 * notification posting, or speech/language certification.
 */
class BrandSurfaceJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    private fun paint(f: MainActivityJourneyFixture, name: String) {
        compose.mainClock.advanceTimeBy(300)
        compose.waitForIdle()
        repeat(2) {
            val latch = CountDownLatch(1)
            f.instrumentation.runOnMainSync {
                val root =
                    ActivityLifecycleMonitorRegistry.getInstance()
                        .getActivitiesInStage(Stage.RESUMED)
                        .single()
                        .window
                        .decorView
                root.viewTreeObserver.registerFrameCommitCallback { latch.countDown() }
                root.invalidate()
            }
            check(latch.await(3, TimeUnit.SECONDS))
        }
        // Compose's virtual clock does not drive SystemUI tint animation.
        android.os.SystemClock.sleep(600)
        var bars = 0
        var ime = false
        var expectedLight = false
        f.instrumentation.runOnMainSync {
            val host =
                ActivityLifecycleMonitorRegistry.getInstance()
                    .getActivitiesInStage(Stage.RESUMED)
                    .single()
            bars = host.window.insetsController!!.systemBarsAppearance
            ime =
                host.window.decorView.rootWindowInsets.isVisible(
                    android.view.WindowInsets.Type.ime()
                )
            expectedLight =
                f.model.appearance == Appearance.LIGHT ||
                    (f.model.appearance == Appearance.SYSTEM &&
                        (f.base.resources.configuration.uiMode and
                            android.content.res.Configuration.UI_MODE_NIGHT_MASK) !=
                            android.content.res.Configuration.UI_MODE_NIGHT_YES)
        }
        File(f.output, "$name-system-bars.json")
            .writeText(
                JSONObject()
                    .put("appearance_bits", bars)
                    .put("expected_light_bars", expectedLight)
                    .put("ime_visible", ime)
                    .put("native_settle_ms", 600)
                    .toString(2)
            )
        f.capture(name)
        if (!ime)
            assertEquals(
                "Actual settled activity navigation-bar appearance",
                expectedLight,
                bars and android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS != 0,
            )
    }

    @Test
    fun approvedBrandAndGuavaWelcomeLanguageAndAccountRenderWithoutSignIn(): Unit = runBlocking {
        MainActivityJourneyFixture("brand-onboarding").use { f ->
            try {
                val local = LocalTranslation()
                val before =
                    try {
                        withTimeout(10_000) { local.isReady("en", "es") }
                    } finally {
                        local.close()
                    }
                val icon = f.base.packageManager.getApplicationIcon(BuildConfig.APPLICATION_ID)
                assertTrue(icon is AdaptiveIconDrawable)
                val mask =
                    requireNotNull(
                        ResourcesCompat.getDrawable(
                            f.base.resources,
                            R.drawable.vipi_notification,
                            null,
                        )
                    )
                val bitmap = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
                mask.setBounds(0, 0, 96, 96)
                mask.draw(Canvas(bitmap))
                var visible = 0
                for (y in 0 until 96) for (x in 0 until 96) {
                    val px = bitmap.getPixel(x, y)
                    if (android.graphics.Color.alpha(px) > 0) {
                        visible++
                        assertEquals(0xFFFFFF, px and 0xFFFFFF)
                    }
                }
                assertTrue(visible in 1 until 96 * 96)
                bitmap.recycle()
                File(f.output, "native-assets.json")
                    .writeText(
                        JSONObject()
                            .put("adaptive_class", icon.javaClass.name)
                            .put("white_alpha_mask_visible_samples", visible)
                            .put("notification_posted", false)
                            .toString(2)
                    )
                f.launch()
                compose.waitUntil(15_000) { f.model.screen == Screen.WELCOME }
                // Inspect the real preview immediately. The app owns normal model
                // preparation; this visual journey must not wait offscreen for it.
                compose.mainClock.advanceTimeBy(500)
                compose.waitForIdle()
                val probe = LocalTranslation()
                val after =
                    try {
                        withTimeout(10_000) { probe.isReady("en", "es") }
                    } finally {
                        probe.close()
                    }
                var translated = false
                f.instrumentation.runOnMainSync {
                    translated =
                        f.paragraphs().any {
                            it.originalMessage == OnboardingPreviewSource.text("en") &&
                                it.text.toString() != it.originalMessage
                        }
                }
                File(f.output, "preview-preparation.json")
                    .writeText(
                        JSONObject()
                            .put("source", "en")
                            .put("target", "es")
                            .put("already_present", before)
                            .put("ready_at_capture", after)
                            .put("translated_at_capture", translated)
                            .put(
                                "preparation_owner",
                                "actual ConversationPreview, no offscreen forced wait",
                            )
                            .put("acoustic_quality_claim", false)
                            .toString(2)
                    )
                for ((mode, label) in
                    listOf(
                        Appearance.LIGHT to "01-welcome-day",
                        Appearance.DARK to "02-welcome-night",
                    )) {
                    compose.runOnIdle { f.model.changeAppearance(mode) }
                    paint(f, label)
                }
                compose
                    .onNodeWithText(f.base.getString(R.string.choose_languages))
                    .apply {
                        if (f.base.resources.configuration.fontScale >= 1.5f) performScrollTo()
                    }
                    .assertIsDisplayed()
                    .performClick()
                compose.waitUntil(5_000) { f.model.screen == Screen.LANGUAGE }
                paint(f, "03-language-night")
                compose.runOnIdle { f.model.changeAppearance(Appearance.LIGHT) }
                paint(f, "04-language-day")
                compose
                    .onNodeWithText(f.base.getString(R.string.continue_action))
                    .apply {
                        if (f.base.resources.configuration.fontScale >= 1.5f) performScrollTo()
                    }
                    .assertIsDisplayed()
                    .performClick()
                compose.waitUntil(5_000) { f.model.screen == Screen.ACCOUNT }
                paint(f, "05-account-day")
                compose
                    .onNodeWithText(f.base.getString(R.string.continue_signin))
                    .apply {
                        if (f.base.resources.configuration.fontScale >= 1.5f) performScrollTo()
                    }
                    .assertIsNotEnabled()
                assertNull(f.model.authentication.userID)
                f.device.pressBack()
                compose.waitUntil(5_000) { f.model.screen == Screen.LANGUAGE }
                paint(f, "06-return-language")
            } catch (e: Throwable) {
                runCatching { paint(f, "failure") }
                throw e
            } finally {
                f.stopActivity()
            }
        }
    }

    @Test
    fun guavaSettingsAndAddFriendUseRealRootInBothAppearances() {
        val services =
            JourneyServices(
                profileRequired = false,
                accountDisplayName = "Alex",
                peerDisplayName = "Maya",
            )
        MainActivityJourneyFixture("brand-settings", services::model).use { f ->
            try {
                f.launch()
                compose.waitUntil(15_000) {
                    f.model.screen == Screen.HOME && f.model.chat?.ready == true
                }
                compose
                    .onNodeWithContentDescription(f.base.getString(R.string.nav_settings))
                    .performClick()
                compose.waitUntil(5_000) { f.model.screen == Screen.SETTINGS }
                for ((mode, label) in
                    listOf(
                        Appearance.LIGHT to "01-settings-day",
                        Appearance.DARK to "02-settings-night",
                    )) {
                    compose.runOnIdle { f.model.changeAppearance(mode) }
                    paint(f, label)
                }
                f.device.pressBack()
                compose.waitUntil(5_000) { f.model.screen == Screen.HOME }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.waitUntil(5_000) { f.model.screen == Screen.NEW_CHAT }
                for ((mode, label) in
                    listOf(
                        Appearance.LIGHT to "03-new-chat-day",
                        Appearance.DARK to "04-new-chat-night",
                    )) {
                    compose.runOnIdle { f.model.changeAppearance(mode) }
                    paint(f, label)
                }
                services.assertNoPurchase()
            } catch (e: Throwable) {
                runCatching { paint(f, "failure") }
                throw e
            } finally {
                f.stopActivity()
                services.close()
            }
        }
    }
}
