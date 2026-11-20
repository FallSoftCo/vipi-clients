package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/** Actual Settings, app root, owner shutdown, persisted recovery and real
 * account-scoped encrypted erasure. Only the deletion service is synthetic. */
class RootDeletionJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun cancelThenLostDeletionReplyReopensOnlyRecoveryAndErasesConfirmedAccount() {
        lateinit var services: JourneyServices
        var submitted: DeletionRecord? = null
        val submits = AtomicInteger(); val statuses = AtomicInteger()
        val complete = AtomicBoolean(false)
        val api = object : DeletionTransport {
            override suspend fun submit(record: DeletionRecord): JSONObject {
                assertEquals(1, submits.incrementAndGet())
                assertEquals(services.account, record.account); assertEquals(services.subject, record.userID)
                submitted = record
                throw IOException("Synthetic accepted request lost its response")
            }
            override suspend fun status(record: DeletionRecord): JSONObject {
                statuses.incrementAndGet()
                val accepted = submitted ?: throw ServiceFailure(404, "deletion_receipt_unavailable")
                assertEquals(accepted, record)
                if (!complete.get()) throw IOException("Synthetic recovery transport unavailable")
                return JSONObject().put("account_id", record.account).put("status", "deleted")
            }
        }
        services = JourneyServices(profileRequired = false, seedBotMessages = 70, deletionService = api)
        MainActivityJourneyFixture("root-deletion", services::model).use { f ->
            val other = UUID.randomUUID()
            fun screen(value: Screen) = compose.waitUntil(10_000) { f.model.screen == value }
            fun ime(): Boolean {
                var visible = false
                f.instrumentation.runOnMainSync {
                    visible = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                        view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it)
                            .isVisible(WindowInsetsCompat.Type.ime()) } == true
                    }
                }
                return visible
            }
            fun keyExists(id: UUID) = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
                .containsAlias("co.fallsoft.vipi.messages.$id")
            fun deleteButton() = compose.onNode(hasText(f.base.getString(R.string.ui_a2e20a335700)) and hasClickAction())
            val ownedDirectory = File(f.isolated.noBackupFilesDir, "messages/${services.account}")
            try {
                MessageVault(f.isolated, other).use { vault -> vault.transaction { vault.put("test", "preserved", "other-account".toByteArray()) } }
                f.launch(); screen(Screen.HOME)
                compose.onNodeWithText(f.base.getString(R.string.ui_f173182378d0)).performScrollTo().performTouchInput { click() }
                screen(Screen.BOT)
                compose.waitUntil(10_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED && f.model.bot?.allowance != null }
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { ime() }
                compose.onNodeWithTag("bot-message-input").performTextInput("A synthetic pending reply before account deletion.")
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(8_000) { services.botPosts.get() == 1 && f.model.bot?.busy == true }
                if (ime()) f.device.pressBack()
                compose.waitUntil(5_000) { !ime() }
                f.device.pressBack(); screen(Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performTouchInput { click() }
                screen(Screen.SETTINGS)
                deleteButton().performScrollTo().performTouchInput { click() }; screen(Screen.DELETE_ACCOUNT)
                compose.onNodeWithText(f.base.getString(R.string.deletion_fallsoft_retained)).performScrollTo().assertIsDisplayed()
                deleteButton().performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("delete-confirm").assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.cancel_action)).performTouchInput { click() }
                compose.onNodeWithTag("delete-confirm").assertDoesNotExist()
                compose.runOnIdle {
                    assertEquals(0, submits.get()); assertEquals(0, statuses.get())
                    assertFalse(f.model.deletion.active); assertTrue(f.model.bot?.busy == true)
                    assertTrue(ownedDirectory.exists()); assertTrue(keyExists(services.account)); assertTrue(keyExists(other))
                }
                f.capture("01-cancel-does-not-close-or-delete")
                deleteButton().performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("delete-confirm").performTouchInput { click() }
                compose.waitUntil(10_000) {
                    submits.get() == 1 && services.cancelledBotPosts.get() == 1 &&
                        f.model.deletion.notice == R.string.deletion_request_unconfirmed && !f.model.deletion.busy
                }
                compose.runOnIdle {
                    assertNull(f.model.chat); assertNull(f.model.bot); assertNull(f.model.subscriptions)
                    assertTrue(f.model.deletion.active); assertTrue(ownedDirectory.exists())
                    assertEquals(DeletionRecord.Phase.PREPARED, PrivateDeletionStore(f.isolated).load()?.phase)
                }
                compose.onNodeWithText(f.base.getString(R.string.deletion_request_unconfirmed)).assertIsDisplayed()
                f.capture("02-lost-reply-enters-deletion-only-root")
                val oldModel = f.model
                f.relaunch { application -> VipiModel(application, NoJourneyModelTranslation, services) }
                compose.waitUntil(10_000) {
                    f.model !== oldModel && f.model.deletion.active && !f.model.deletion.busy &&
                        f.model.deletion.notice == R.string.deletion_request_unconfirmed
                }
                compose.runOnIdle {
                    assertEquals(submitted, f.model.deletion.pending)
                    assertNull(f.model.chat); assertNull(f.model.bot); assertNull(f.model.subscriptions)
                    assertEquals(1, services.deviceRegistrations.get()); assertEquals(1, submits.get())
                }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).assertDoesNotExist()
                compose.onNodeWithTag("bot-message-input").assertDoesNotExist()
                f.capture("03-fresh-owner-recovers-persisted-deletion-only")
                complete.set(true)
                compose.onNodeWithText(f.base.getString(R.string.ui_eb55b8291994)).performScrollTo().performTouchInput { click() }
                compose.waitUntil(10_000) { f.model.deletion.pending?.localErased == true && !f.model.deletion.busy }
                compose.runOnIdle {
                    assertEquals(DeletionRecord.Phase.COMPLETED, f.model.deletion.pending?.phase)
                    assertEquals(1, submits.get()); assertTrue(statuses.get() >= 3)
                    assertFalse(ownedDirectory.exists()); assertFalse(keyExists(services.account)); assertTrue(keyExists(other))
                    assertNull(f.model.authentication.userID)
                }
                MessageVault(f.isolated, other).use { vault ->
                    vault.transaction {
                        assertEquals("other-account", vault.get("test", "preserved")?.toString(Charsets.UTF_8))
                    }
                }
                services.botReplyGate.complete(Unit)
                compose.waitForIdle()
                assertFalse("Cancelled Bot work cannot recreate the erased account", ownedDirectory.exists())
                assertEquals(1, services.cancelledBotPosts.get())
                f.capture("04-confirmed-account-erased-other-account-preserved")
                compose.onNodeWithText(f.base.getString(R.string.ui_11a6767d5674)).performScrollTo().performTouchInput { click() }
                screen(Screen.WELCOME)
                assertNull(PrivateDeletionStore(f.isolated).load())
                f.relaunch { application -> VipiModel(application, NoJourneyModelTranslation, services) }
                screen(Screen.WELCOME)
                compose.runOnIdle {
                    assertFalse(f.model.deletion.active); assertNull(f.model.authentication.userID)
                    assertNull(f.model.chat); assertEquals(1, submits.get()); services.assertNoPurchase()
                }
                f.capture("05-done-stays-signed-out-after-new-owner")
                File(f.output, "receipt.json").writeText(JSONObject().put("actual_settings_and_root", true)
                    .put("fresh_models_over_same_private_disk", 2).put("cancel_deletion_requests", 0)
                    .put("submit_count", submits.get()).put("status_count", statuses.get())
                    .put("pending_bot_request_cancelled", 1).put("real_owned_vault_and_key_erased", true)
                    .put("unrelated_account_preserved", true).put("recovery_used_original_receipt", true)
                    .put("done_signed_out_after_relaunch", true).put("live_account_or_global_deletion", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally {
                f.stopActivity(); services.botReplyGate.complete(Unit); services.close()
                KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$other") }
            }
        }
    }
}
