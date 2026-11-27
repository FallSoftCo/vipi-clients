package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Scaffold
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
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class AccountDeletionUIDeviceTest {
    @get:Rule val compose = createComposeRule()

    private class Store : DeletionStore {
        var record: DeletionRecord? = null

        override fun load() = record

        override fun save(record: DeletionRecord) {
            this.record = record
        }

        override fun remove() {
            record = null
        }
    }

    private class Transport : DeletionTransport {
        var accepted = false
        var finished = false
        var offline = true
        var submissions = 0

        override suspend fun status(record: DeletionRecord): JSONObject {
            if (offline) throw IOException()
            if (!accepted) throw ServiceFailure(404, "deletion_receipt_unavailable")
            return JSONObject()
                .put("account_id", record.account)
                .put("status", if (finished) "deleted" else "deletion_requested")
        }

        override suspend fun submit(record: DeletionRecord): JSONObject {
            submissions++
            accepted = true
            return status(record)
        }
    }

    @Test
    fun confirmCancelRetryAndFinishWithThemesAndLargeType() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiDeletionRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "deletion-ui-$run")
        check(!output.exists())
        output.mkdirs()
        val root = File(base.cacheDir, "deletion-ui-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = root
            }
        val store = Store()
        val api = Transport()
        var erased = 0
        var done = false
        lateinit var deletion: AccountDeletion
        val theme = mutableStateOf(Appearance.LIGHT)
        val font = mutableStateOf(1f)
        val visible = mutableStateOf(true)
        runBlocking {
            withContext(Dispatchers.Main) {
                deletion = AccountDeletion(store, api, { erased++ }, {})
            }
        }
        fun capture(name: String) {
            compose.waitForIdle()
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            device.waitForIdle(1000)
            android.os.SystemClock.sleep(350)
            check(device.takeScreenshot(File(output, "$name.png")))
        }
        try {
            compose.setContent {
                if (visible.value) {
                    val scope = rememberCoroutineScope()
                    CompositionLocalProvider(
                        LocalDensity provides Density(LocalDensity.current.density, font.value)
                    ) {
                        VipiTheme(theme.value) {
                            if (deletion.active)
                                AccountDeletionProgress(
                                    deletion,
                                    remember { Authentication(context) },
                                ) {
                                    done = true
                                }
                            else
                                Scaffold { insets ->
                                    Column(
                                        Modifier.fillMaxSize()
                                            .padding(insets)
                                            .verticalScroll(rememberScrollState())
                                            .padding(26.dp),
                                        verticalArrangement = Arrangement.spacedBy(24.dp),
                                    ) {
                                        DeleteAccountScreen {
                                            deletion.begin(
                                                UUID.randomUUID(),
                                                "user_synthetic_ui",
                                            ) {}
                                            scope.launch { deletion.resume() }
                                        }
                                    }
                                }
                        }
                    }
                }
            }
            capture("android-deletion-explanation-light")
            compose
                .onNode(hasText("Delete Vipi account") and hasClickAction())
                .performScrollTo()
                .performClick()
            compose.onNodeWithText("Delete your Vipi account?").assertIsDisplayed()
            capture("android-deletion-confirm-light")
            compose.onNodeWithText("Cancel").performClick()
            compose.runOnIdle {
                assertNull(store.record)
                assertEquals(0, api.submissions)
                theme.value = Appearance.DARK
            }
            compose
                .onNode(hasText("Delete Vipi account") and hasClickAction())
                .performScrollTo()
                .performClick()
            compose.onNodeWithTag("delete-confirm").performClick()
            compose.onNodeWithText("Continue deletion").performScrollTo().assertIsDisplayed()
            compose.runOnIdle {
                assertNotNull(deletion.notice)
                assertEquals(0, erased)
            }
            capture("android-deletion-interrupted-dark")
            compose.runOnIdle { api.offline = false }
            compose.onNodeWithText("Continue deletion").performClick()
            compose.onNodeWithText("Deletion requested").performScrollTo().assertIsDisplayed()
            compose.runOnIdle {
                assertEquals(1, api.submissions)
                assertEquals(1, erased)
                theme.value = Appearance.LIGHT
                font.value = 1.8f
            }
            capture("android-deletion-requested-large-type")
            compose.onNodeWithText("Check status").performScrollTo().assertIsDisplayed()
            compose.runOnIdle {
                api.finished = true
                font.value = 1f
            }
            compose.onNodeWithText("Check status").performScrollTo().performClick()
            compose.onNodeWithText("Vipi account deleted").performScrollTo().assertIsDisplayed()
            capture("android-deletion-complete-light")
            compose.onNodeWithText("Done").performScrollTo().performClick()
            compose.runOnIdle {
                assertTrue(done)
                assertFalse(deletion.active)
                assertNull(store.record)
            }
            File(output, "receipt.json")
                .writeText(
                    JSONObject()
                        .put("synthetic_transport_and_account", true)
                        .put("live_account_deleted", false)
                        .put("cancel_before_request", true)
                        .put("retry_without_false_success", true)
                        .put("font_scale", 1.8)
                        .put("large_type_action_reachable", true)
                        .toString()
                )
        } finally {
            compose.runOnIdle { visible.value = false }
            compose.waitForIdle()
            root.deleteRecursively()
        }
    }
}
