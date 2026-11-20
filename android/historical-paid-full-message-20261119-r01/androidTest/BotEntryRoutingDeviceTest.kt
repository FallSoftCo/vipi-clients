package co.fallsoft.vipi

import android.app.Application
import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.MutableState
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

/** Actual synchronous entry navigation; no auth records, activation, sends or network. */
class BotEntryRoutingDeviceTest {
    private class Fixture {
        private val base = InstrumentationRegistry.getInstrumentation().targetContext
        private val prefix = "bot-entry-${UUID.randomUUID()}-"
        private val root = File(base.cacheDir, prefix).apply { mkdirs() }
        private val preferences = mutableSetOf<String>()
        val application = object : Application() {
            init { attachBaseContext(base) }
            override fun getApplicationContext(): Context = this
            override fun getNoBackupFilesDir(): File = root
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
                preferences += prefix + name
                return base.getSharedPreferences(prefix + name, mode)
            }
        }
        private val translator = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model preparation")
            override suspend fun translate(text: String, source: String, target: String): String = error("No translation")
            override fun close() = Unit
        }
        val model = VipiModel(application, translator)
        val account = UUID.randomUUID()
        var requests = 0
        private val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                requests++
                error("Entry navigation must not activate/register/send: $method $path")
            }
        }
        private val chats = mutableListOf<ChatSession>()
        fun signedIn(user: String?) = state(model.authentication, "userID", user)
        fun chat(user: String = "synthetic-current-user", profile: Boolean = false,
            needsProfile: Boolean = false, ready: Boolean = false, revoked: Boolean = false): ChatSession {
            val chat = ChatSession(application, api, user).also { chats += it }
            if (profile) state(chat, "profile", ChatProfile(account, "synthetic_user", "Synthetic"))
            state(chat, "needsProfile", needsProfile)
            state(chat, "ready", ready)
            state(chat, "needsDeviceRecovery", revoked)
            state(model, "chat", chat)
            return chat
        }
        fun close() {
            model.bot?.close()
            chats.forEach { it.close() }
            assertEquals(0, requests)
            root.deleteRecursively()
            preferences.forEach { base.deleteSharedPreferences(it) }
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
        companion object {
            private fun state(target: Any, name: String, value: Any?) {
                val field = target.javaClass.getDeclaredField("${name}\$delegate").apply { isAccessible = true }
                @Suppress("UNCHECKED_CAST")
                (field.get(target) as MutableState<Any?>).value = value
            }
        }
    }
    private fun fixture(block: (Fixture) -> Unit) {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val value = Fixture()
            try { block(value) } finally { value.close() }
        }
    }

    @Test fun signedOutEntryShowsAccountInsteadOfBotPlanEvenWithCachedProfile() = fixture { f ->
        f.signedIn(null)
        f.chat(user = "synthetic-previous-user", profile = true, ready = true)
        f.model.navigate(Screen.HOME)
        f.model.openBot()
        assertEquals(Screen.ACCOUNT, f.model.screen)
        assertNull(f.model.bot)
    }

    @Test fun authenticatedProfileRequiredShowsUsernameSetupInsteadOfPaywall() = fixture { f ->
        f.signedIn("synthetic-current-user")
        f.chat(needsProfile = true)
        f.model.openBot()
        assertEquals(Screen.PROFILE, f.model.screen)
        assertNull(f.model.bot)
        f.chat(profile = true, needsProfile = true, ready = true)
        f.model.openBot()
        assertEquals(Screen.PROFILE, f.model.screen)
    }

    @Test fun absentProfileReturnsToExistingHomeConnectionRecoveryWithoutActivation() = fixture { f ->
        f.signedIn("synthetic-current-user")
        f.model.openBot()
        assertEquals(Screen.HOME, f.model.screen)
        assertNull(f.model.bot)
        f.chat()
        f.model.openBot()
        assertEquals(Screen.HOME, f.model.screen)
        assertNull(f.model.bot)
        assertEquals(0, f.requests)
    }

    @Test fun otherAccountCachedProfileCannotOpenBotOrMasqueradeAsReadyHome() = fixture { f ->
        f.signedIn("synthetic-current-user")
        f.chat(user = "synthetic-previous-user", profile = true, ready = true)
        f.model.openBot()
        assertEquals(Screen.HOME, f.model.screen)
        assertNotNull(f.model.chatError) // Home displays its retry card, not old threads.
        assertNull(f.model.bot)
    }

    @Test fun correctlyBoundRevokedDeviceStillReadsSavedBotDraftWithoutSend() = fixture { f ->
        f.signedIn("synthetic-current-user")
        f.chat(profile = true, ready = false, revoked = true)
        f.model.openBot()
        assertEquals(Screen.BOT, f.model.screen)
        val bot = requireNotNull(f.model.bot)
        bot.saveDraft("Saved local draft")
        f.model.navigate(Screen.HOME)
        f.model.openBot()
        assertEquals(Screen.BOT, f.model.screen)
        assertSame(bot, f.model.bot)
        assertEquals("Saved local draft", f.model.bot?.draft)
        assertTrue(f.model.bot?.messages?.isEmpty() == true)
        assertEquals(0, f.requests)
    }
}
