package co.fallsoft.vipi

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import java.io.File
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class LanguageDownloadsUiTest {
    @get:Rule val compose = createComposeRule()

    @Test
    fun chooseLanguagesManageDownloadsAndReadAtLargeText() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val device = UiDevice.getInstance(instrumentation)
        val output = File(instrumentation.targetContext.filesDir, "language-downloads-ui-002")
        check(!output.exists())
        output.mkdirs()
        val source = mutableStateOf("en")
        val target = mutableStateOf("sw")
        val theme = mutableStateOf(Appearance.LIGHT)
        val scale = mutableFloatStateOf(1f)
        val visible = mutableStateOf(true)
        val store =
            object : LanguageDownloadStore {
                var models = setOf("sw", "es")

                override suspend fun installed(pair: DownloadPair) = models.intersect(pair.models)

                override suspend fun download(pair: DownloadPair, cellular: Boolean) {
                    models = models + pair.models
                }

                override suspend fun remove(pair: DownloadPair) {
                    models = models - pair.models
                }

                override fun close() = Unit
            }
        val downloads = LanguageDownloads(store)
        fun capture(name: String) {
            compose.waitForIdle()
            device.waitForIdle()
            instrumentation.waitForIdleSync()
            // Native popup/dialog windows finish their dismissal outside the Compose test clock.
            android.os.SystemClock.sleep(400)
            check(device.takeScreenshot(File(output, name)))
        }
        compose.setContent {
            if (visible.value)
                CompositionLocalProvider(
                    LocalDensity provides Density(LocalDensity.current.density, scale.floatValue)
                ) {
                    VipiTheme(theme.value) {
                        androidx.compose.material3.Surface {
                            Column(
                                Modifier.fillMaxSize()
                                    .safeDrawingPadding()
                                    .verticalScroll(rememberScrollState())
                                    .padding(20.dp)
                            ) {
                                LanguageDownloadsContent(
                                    source.value,
                                    target.value,
                                    {
                                        source.value = it
                                        if (target.value == it)
                                            target.value = if (it == "en") "es" else "en"
                                    },
                                    { target.value = it },
                                    downloads,
                                )
                            }
                        }
                    }
                }
        }
        try {
            compose
                .onNodeWithText("English and Swahili are ready for offline translation.")
                .assertIsDisplayed()
            capture("android-languages-light.png")
            compose.onNodeWithContentDescription("I already speak").performClick()
            compose.onNodeWithText("Spanish · Español").performClick()
            compose
                .onNodeWithText("Spanish and Swahili are ready for offline translation.")
                .assertIsDisplayed()
            compose.runOnIdle { theme.value = Appearance.DARK }
            compose.waitForIdle()
            capture("android-languages-dark.png")
            compose.onNodeWithContentDescription("I want to learn").performClick()
            compose.onNodeWithText("Japanese · 日本語").performClick()
            compose.onNodeWithText("Download languages").performScrollTo().performClick()
            compose
                .onNodeWithText("Spanish and Japanese are ready for offline translation.")
                .performScrollTo()
                .assertIsDisplayed()
            compose.onNodeWithText("Remove translation downloads").performScrollTo().performClick()
            compose.onNodeWithText("Keep downloads").performClick()
            compose.onNodeWithText("Remove translation downloads").performClick()
            compose.onNodeWithText("Remove", useUnmergedTree = true).performClick()
            compose.onNodeWithText("Download languages").performScrollTo().assertIsDisplayed()
            compose.onNodeWithText("Remove downloads?").assertDoesNotExist()
            device.waitForIdle()
            android.os.SystemClock.sleep(400)
            compose.runOnIdle { scale.floatValue = 2f }
            compose.waitForIdle()
            compose.onNodeWithText("Download languages").performScrollTo().assertIsDisplayed()
            capture("android-languages-large.png")
            assertEquals(emptySet<String>(), downloads.installed)
            File(output, "receipt.json")
                .writeText(
                    """{"ui_store":"controlled fixture","native_store_verified_separately":true,"language_selection":true,"remove_confirmation_and_cancel":true,"light_dark_large_text":true,"real_download_or_removal_performed":false}"""
                )
        } finally {
            compose.runOnIdle {
                visible.value = false
                downloads.close()
            }
            compose.waitForIdle()
        }
    }
}
