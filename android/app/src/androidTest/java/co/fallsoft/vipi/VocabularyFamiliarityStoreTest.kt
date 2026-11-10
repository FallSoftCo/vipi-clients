package co.fallsoft.vipi

import androidx.test.core.app.ApplicationProvider
import co.fallsoft.vipi.core.SourceReferencePresentation
import co.fallsoft.vipi.core.SourceReferenceUnit
import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.security.KeyStore
import java.util.UUID

class VocabularyFamiliarityStoreTest {
    @Test fun encryptedExposureSurvivesReopenAndSeparatesPairs() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val account = UUID.randomUUID()
        val spans = requireNotNull(SourceReferencePresentation.create("tea", "sw", listOf(
            SourceReferenceUnit(0,3,"tea","chai",null,"qa-tea","a".repeat(64),nativeSourceTokens=1)),1.0,1)).spans
        val vault = MessageVault(context, account)
        try {
            val store = VocabularyFamiliarityStore(vault)
            for (day in 100..103) {
                assertTrue(store.observe(spans,"en","sw",day)); assertTrue(store.observe(spans,"en","sw",day))
            }
            assertEquals(6000L,store.targetMilliseconds(spans,"en","sw",103))
            vault.close()
            assertFalse(store.observe(spans,"en","sw",104))
            MessageVault(context,account).use { reopened ->
                val restored = VocabularyFamiliarityStore(reopened)
                assertEquals(6000L,restored.targetMilliseconds(spans,"en","sw",103))
                assertEquals(4500L,restored.targetMilliseconds(spans,"en","es",103))
                reopened.transaction {
                    val ids = reopened.ids("immersion-exposure")
                    assertEquals(1,ids.size); assertEquals(64,ids.single().length)
                    val guessable = java.security.MessageDigest.getInstance("SHA-256").digest("v1\u0000en\u0000sw\u0000tea\u0000chai".toByteArray()).joinToString("") { "%02x".format(it) }
                    assertNotEquals(guessable, ids.single())
                    assertEquals(32, requireNotNull(reopened.get("immersion-metadata", "id-key-v1")).size)
                    val bytes = requireNotNull(reopened.get("immersion-exposure",ids.single())).toString(Charsets.UTF_8)
                    assertEquals(4,JSONObject(bytes).getInt("exposureDays")); assertFalse(bytes.contains("tea"))
                }
            }
        } finally {
            runCatching { vault.close() }
            vault.file.parentFile!!.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry("co.fallsoft.vipi.messages.$account")
        }
    }
}
