package co.fallsoft.vipi

import android.net.Uri
import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.io.File
import java.util.UUID

class SignInProviderDeviceTest {
    private val start = "https://api.workos.com/user_management/authorize?client_id=client_fixture&redirect_uri=co.fallsoft.vipi%3A%2F%2Fauth%2Fcallback&response_type=code&state=state%2Bfixture&code_challenge=challenge_fixture&code_challenge_method=S256&provider=old&provider=other&max_age=90&screen_hint=sign-up"

    @Test fun providerSelectionPreservesOriginalPKCEStateAndExactCallback() {
        for (provider in SignInProvider.entries) {
            val url = signInAuthorizationURL(start, provider, reauthenticate = false)
            val original = Uri.parse(start)
            assertEquals(listOf(provider.workosProvider), url.getQueryParameters("provider"))
            for (name in listOf("client_id", "redirect_uri", "response_type", "state", "code_challenge", "code_challenge_method")) {
                assertEquals(original.getQueryParameters(name), url.getQueryParameters(name))
            }
            assertNull(url.getQueryParameter("max_age"))
            assertNull(url.getQueryParameter("screen_hint"))
            assertNull(url.getQueryParameter("client_secret"))
            assertEquals(original.scheme, url.scheme)
            assertEquals(original.authority, url.authority)
            assertEquals(original.path, url.path)
        }
    }

    @Test fun sameAccountReauthenticationAlwaysUsesAuthKitFreshFactorSelection() {
        for (provider in SignInProvider.entries) {
            val url = signInAuthorizationURL(start, provider, reauthenticate = true)
            assertEquals(listOf("authkit"), url.getQueryParameters("provider"))
            assertEquals(listOf("0"), url.getQueryParameters("max_age"))
            assertEquals(listOf("sign-in"), url.getQueryParameters("screen_hint"))
            assertEquals("state+fixture", url.getQueryParameter("state"))
            assertEquals("challenge_fixture", url.getQueryParameter("code_challenge"))
        }
    }
}

class IdentityAuthorityDeviceTest {
    @Test fun legacyRecordsRemainPinnedAndTaggedRecordsRoundTripWithoutChangingBinding() {
        val legacy = JSONObject().put("userID", "user_original_fixture").put("refreshToken", "synthetic-refresh")
        assertEquals(IdentityAuthority.legacy, IdentityAuthority.read(legacy))
        for (authority in IdentityAuthority.entries) {
            val restored = JSONObject(authority.tag(JSONObject(legacy.toString())).toString())
            assertEquals(authority, IdentityAuthority.read(restored))
            assertEquals(authority.clientID, restored.getString("clientID"))
            assertEquals("user_original_fixture", restored.getString("userID"))
            assertEquals("synthetic-refresh", restored.getString("refreshToken"))
            assertFalse(restored.has("client_secret"))
        }
    }
    @Test fun unknownMismatchedPartialAndFutureAuthorityMetadataFailClosed() {
        val invalid = listOf(
            JSONObject().put("formatVersion", 2).put("authority", "unknown").put("clientID", IdentityAuthority.VIPI_PRODUCTION.clientID),
            IdentityAuthority.VIPI_PRODUCTION.tag(JSONObject()).put("clientID", IdentityAuthority.VIPI_STAGING.clientID),
            IdentityAuthority.VIPI_PRODUCTION.tag(JSONObject()).put("formatVersion", 3),
            JSONObject().put("authority", IdentityAuthority.VIPI_PRODUCTION.recordID),
            JSONObject().put("clientID", IdentityAuthority.VIPI_PRODUCTION.clientID), JSONObject().put("formatVersion", 2)
        )
        for (record in invalid) assertTrue(runCatching { IdentityAuthority.read(record) }.isFailure)
    }
    @Test fun savedAuthorityControlsReauthenticationEvenWhenBuildConfigurationChanges() {
        for (authority in IdentityAuthority.entries) {
            assertEquals(authority, IdentityAuthority.forSignIn(authority, true, "client_unknown_future"))
            assertEquals(authority, IdentityAuthority.forSignIn(authority, false, ""))
            assertEquals(authority, IdentityAuthority.forSignIn(null, false, authority.clientID))
        }
        assertEquals(IdentityAuthority.legacy, IdentityAuthority.forSignIn(null, true, "client_unknown_future"))
        assertTrue(runCatching { IdentityAuthority.forSignIn(null, false, "client_unknown_future") }.isFailure)
    }
}

class IdentityAuthorityExchangeDeviceTest {
    @Test fun refreshUsesSavedClientAndCrossAuthorityCallbackCannotReplaceAccount() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "authority-${UUID.randomUUID()}")
        val context = object : ContextWrapper(base) {
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val records = PrivateRecords(context)
        val subject = "user_original_fixture"
        val authority = IdentityAuthority.VIPI_PRODUCTION
        records.write("session", authority.tag(JSONObject().put("userID", subject).put("accessToken", "synthetic-old-access").put("refreshToken", "synthetic-old-refresh")))
        val auth = Authentication(context)
        fun result() = JSONObject().put("user", JSONObject().put("id", subject)).put("access_token", "synthetic-new-access").put("refresh_token", "synthetic-new-refresh")
        try {
            var exchanges = 0
            auth.qualificationExchange = { fields ->
                exchanges++
                assertEquals(authority.clientID, fields.getString("client_id"))
                assertEquals("synthetic-old-refresh", fields.getString("refresh_token"))
                assertFalse(fields.has("client_secret"))
                result()
            }
            runBlocking { withContext(Dispatchers.Main) { assertEquals("synthetic-new-access", auth.accessToken(subject, "synthetic-old-access")) } }
            assertEquals(1, exchanges)
            assertEquals(authority, IdentityAuthority.read(requireNotNull(records.read("session"))))
            val savedBytes = File(context.noBackupFilesDir, "private-records/session").readBytes()
            records.write("pending-sign-in", IdentityAuthority.VIPI_STAGING.tag(JSONObject().put("state", "synthetic-state").put("verifier", "synthetic-verifier").put("createdAt", System.currentTimeMillis()).put("expectedUser", subject)))
            auth.qualificationExchange = { fields ->
                exchanges++
                assertEquals(IdentityAuthority.VIPI_STAGING.clientID, fields.getString("client_id"))
                result()
            }
            runBlocking { withContext(Dispatchers.Main) { auth.complete(Uri.parse("co.fallsoft.vipi://auth/callback?state=synthetic-state&code=synthetic-code")) } }
            assertEquals(2, exchanges)
            assertEquals(subject, auth.userID)
            assertNotNull(auth.error)
            assertArrayEquals(savedBytes, File(context.noBackupFilesDir, "private-records/session").readBytes())
        } finally { root.deleteRecursively() }
    }
}
