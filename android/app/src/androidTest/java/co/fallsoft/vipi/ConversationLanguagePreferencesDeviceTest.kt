package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ConversationLanguagePreferencesDeviceTest {
    @Test
    fun directAndGroupOverridesAreEncryptedNamespacedAndDurable() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root =
            java.io.File(base.cacheDir, "conversation-languages-${UUID.randomUUID()}").apply {
                check(mkdirs())
            }
        val context =
            object : android.content.ContextWrapper(base) {
                override fun getNoBackupFilesDir() = root
            }
        val account = UUID.randomUUID()
        // A direct peer and a group can legitimately share a UUID on different
        // surfaces. Their preferences must still remain separate.
        val sharedID = UUID.randomUUID()
        val direct = ConversationRef.Direct(sharedID)
        val group = ConversationRef.Group(sharedID)
        try {
            MessageVault(context, account).use { vault ->
                val store = ConversationLanguageStore(vault)
                store.set(direct, "fr")
                store.set(group, "ja")
                assertEquals("fr", store.all()[direct.storageKey])
                assertEquals("ja", store.all()[group.storageKey])
            }
            MessageVault(context, account).use { vault ->
                val store = ConversationLanguageStore(vault)
                assertEquals(
                    mapOf(direct.storageKey to "fr", group.storageKey to "ja"),
                    store.all(),
                )
                store.clear(direct)
                assertNull(store.all()[direct.storageKey])
                assertEquals("ja", store.all()[group.storageKey])
            }
            MessageVault(context, account).use { vault ->
                assertEquals("ja", ConversationLanguageStore(vault).all()[group.storageKey])
            }
        } finally {
            root.deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
