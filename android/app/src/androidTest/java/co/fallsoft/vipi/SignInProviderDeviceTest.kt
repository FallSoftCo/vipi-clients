package co.fallsoft.vipi

import android.content.ContextWrapper
import android.net.Uri
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SignInProviderDeviceTest {
    private val start =
        "https://api.workos.com/user_management/authorize?client_id=client_fixture&redirect_uri=co.fallsoft.vipi%3A%2F%2Fauth%2Fcallback&response_type=code&state=state%2Bfixture&code_challenge=challenge_fixture&code_challenge_method=S256&provider=old&provider=other&max_age=90&screen_hint=sign-up"

    @Test
    fun providerSelectionPreservesOriginalPKCEStateAndExactCallback() {
        for (provider in SignInProvider.entries) {
            val url = signInAuthorizationURL(start, provider, reauthenticate = false)
            val original = Uri.parse(start)
            assertEquals(listOf(provider.workosProvider), url.getQueryParameters("provider"))
            for (name in
                listOf(
                    "client_id",
                    "redirect_uri",
                    "response_type",
                    "state",
                    "code_challenge",
                    "code_challenge_method",
                )) {
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

    @Test
    fun sameAccountReauthenticationAlwaysUsesAuthKitFreshFactorSelection() {
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
    @Test
    fun legacyRecordsRemainPinnedAndTaggedRecordsRoundTripWithoutChangingBinding() {
        val legacy =
            JSONObject()
                .put("userID", "user_original_fixture")
                .put("refreshToken", "synthetic-refresh")
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

    @Test
    fun unknownMismatchedPartialAndFutureAuthorityMetadataFailClosed() {
        val invalid =
            listOf(
                JSONObject()
                    .put("formatVersion", 2)
                    .put("authority", "unknown")
                    .put("clientID", IdentityAuthority.VIPI_PRODUCTION.clientID),
                IdentityAuthority.VIPI_PRODUCTION.tag(JSONObject())
                    .put("clientID", IdentityAuthority.VIPI_STAGING.clientID),
                IdentityAuthority.VIPI_PRODUCTION.tag(JSONObject()).put("formatVersion", 3),
                JSONObject().put("authority", IdentityAuthority.VIPI_PRODUCTION.recordID),
                JSONObject().put("clientID", IdentityAuthority.VIPI_PRODUCTION.clientID),
                JSONObject().put("formatVersion", 2),
            )
        for (record in invalid) assertTrue(runCatching { IdentityAuthority.read(record) }.isFailure)
    }

    @Test
    fun savedAuthorityControlsReauthenticationEvenWhenBuildConfigurationChanges() {
        for (authority in IdentityAuthority.entries) {
            assertEquals(
                authority,
                IdentityAuthority.forSignIn(authority, true, "client_unknown_future"),
            )
            assertEquals(authority, IdentityAuthority.forSignIn(authority, false, ""))
            assertEquals(authority, IdentityAuthority.forSignIn(null, false, authority.clientID))
        }
        assertEquals(
            IdentityAuthority.legacy,
            IdentityAuthority.forSignIn(null, true, "client_unknown_future"),
        )
        assertTrue(
            runCatching { IdentityAuthority.forSignIn(null, false, "client_unknown_future") }
                .isFailure
        )
    }
}

class IdentityAuthorityExchangeDeviceTest {
    @Test
    fun refreshUsesSavedClientAndCrossAuthorityCallbackCannotReplaceAccount() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "authority-${UUID.randomUUID()}")
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        val records = PrivateRecords(context)
        val subject = "user_original_fixture"
        val authority = IdentityAuthority.VIPI_PRODUCTION
        records.write(
            "session",
            authority.tag(
                JSONObject()
                    .put("userID", subject)
                    .put("accessToken", "synthetic-old-access")
                    .put("refreshToken", "synthetic-old-refresh")
            ),
        )
        val auth = Authentication(context)
        fun result() =
            JSONObject()
                .put("user", JSONObject().put("id", subject))
                .put("access_token", "synthetic-new-access")
                .put("refresh_token", "synthetic-new-refresh")
        try {
            var exchanges = 0
            auth.qualificationExchange = { fields ->
                exchanges++
                assertEquals(authority.clientID, fields.getString("client_id"))
                assertEquals("synthetic-old-refresh", fields.getString("refresh_token"))
                assertFalse(fields.has("client_secret"))
                result()
            }
            runBlocking {
                withContext(Dispatchers.Main) {
                    assertEquals(
                        "synthetic-new-access",
                        auth.accessToken(subject, "synthetic-old-access"),
                    )
                }
            }
            assertEquals(1, exchanges)
            assertEquals(authority, IdentityAuthority.read(requireNotNull(records.read("session"))))
            val savedBytes = File(context.noBackupFilesDir, "private-records/session").readBytes()
            records.write(
                "pending-sign-in",
                IdentityAuthority.VIPI_STAGING.tag(
                    JSONObject()
                        .put("state", "synthetic-state")
                        .put("verifier", "synthetic-verifier")
                        .put("createdAt", System.currentTimeMillis())
                        .put("expectedUser", subject)
                ),
            )
            auth.qualificationExchange = { fields ->
                exchanges++
                assertEquals(IdentityAuthority.VIPI_STAGING.clientID, fields.getString("client_id"))
                result()
            }
            runBlocking {
                withContext(Dispatchers.Main) {
                    auth.complete(
                        Uri.parse(
                            "co.fallsoft.vipi://auth/callback?state=synthetic-state&code=synthetic-code"
                        )
                    )
                }
            }
            assertEquals(2, exchanges)
            assertEquals(subject, auth.userID)
            assertNotNull(auth.error)
            assertArrayEquals(
                savedBytes,
                File(context.noBackupFilesDir, "private-records/session").readBytes(),
            )
        } finally {
            root.deleteRecursively()
        }
    }
}

class IdentityLinkCoordinatorDeviceTest {
    @Test
    fun wrongUUIDReadbackRetainsOldSessionAndExactRetryUsesSameAccountAndRequest() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "identity-link-${UUID.randomUUID()}")
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        val records = PrivateRecords(context)
        val account = UUID.randomUUID()
        val request = UUID.randomUUID()
        val device = UUID.randomUUID()
        val intent =
            IdentityLinkIntent(
                account.toString(),
                request.toString(),
                "user_original_fixture",
                device.toString(),
                "a".repeat(43),
            )
        val candidate =
            IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(
                JSONObject()
                    .put("userID", "user_shared_fixture")
                    .put("accessToken", "synthetic-new-access")
                    .put("refreshToken", "synthetic-new-refresh")
            )
        records.write(
            "session",
            IdentityAuthority.VIPI_PRODUCTION.tag(
                JSONObject()
                    .put("userID", intent.oldUserID)
                    .put("accessToken", "synthetic-old-access")
                    .put("refreshToken", "synthetic-old-refresh")
            ),
        )
        records.write("pending-identity-link", IdentityLinkJournal(intent, candidate).json())
        records.write(
            profileCacheKey(intent.oldUserID),
            JSONObject()
                .put("id", account)
                .put("username", "original_profile")
                .put("display_name", "Synthetic"),
        )
        val auth = Authentication(context)
        var wrongProfile = true
        var posts = 0
        try {
            val original = File(context.noBackupFilesDir, "private-records/session").readBytes()
            auth.qualificationLinkRequest = { method, _, body, token, suppliedDevice ->
                assertEquals(device, suppliedDevice.id)
                if (method == "POST") {
                    posts++
                    assertEquals("synthetic-old-access", token)
                    assertEquals(request.toString(), body!!.getString("request_id"))
                    assertEquals(account.toString(), body.getString("expected_account_id"))
                    assertEquals("synthetic-new-access", body.getString("fallsoft_access_token"))
                    JSONObject()
                        .put("request_id", request)
                        .put("account_id", account)
                        .put("authority_id", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.recordID)
                        .put("authentication_subject", "user_shared_fixture")
                        .put("binding_revision", 1)
                } else {
                    assertEquals("synthetic-new-access", token)
                    JSONObject()
                        .put("id", if (wrongProfile) UUID.randomUUID() else account)
                        .put("username", "original_profile")
                        .put("display_name", "Synthetic")
                }
            }
            runBlocking { withContext(Dispatchers.Main) { auth.resumeFallsoftLink() } }
            assertNotNull(auth.error)
            assertEquals(intent.oldUserID, auth.userID)
            assertArrayEquals(
                original,
                File(context.noBackupFilesDir, "private-records/session").readBytes(),
            )
            assertNotNull(records.read("pending-identity-link"))
            assertNotNull(records.read(profileCacheKey(intent.oldUserID)))
            wrongProfile = false
            runBlocking { withContext(Dispatchers.Main) { auth.resumeFallsoftLink() } }
            assertNull(auth.error)
            assertEquals(2, posts)
            assertEquals("user_shared_fixture", auth.userID)
            assertNull(records.read(profileCacheKey(intent.oldUserID)))
            assertEquals(
                IdentityAuthority.FALLSOFT_VIPI_PRODUCTION,
                IdentityAuthority.read(requireNotNull(records.read("session"))),
            )
            assertNull(records.read("pending-identity-link"))
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun journalRejectsFutureFormatWrongAuthorityTargetAndAccount() {
        val intent =
            IdentityLinkIntent(
                UUID.randomUUID().toString(),
                UUID.randomUUID().toString(),
                "user_original_fixture",
                UUID.randomUUID().toString(),
                "a".repeat(43),
                "user_shared_fixture",
            )
        val candidate =
            IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(
                JSONObject()
                    .put("userID", "user_shared_fixture")
                    .put("accessToken", "synthetic-access")
                    .put("refreshToken", "synthetic-refresh")
            )
        val valid = IdentityLinkJournal(intent, candidate).json()
        assertEquals(
            intent.accountID,
            IdentityLinkJournal.parse(JSONObject(valid.toString())).intent.accountID,
        )
        val invalid =
            listOf(
                JSONObject(valid.toString()).put("linkFormatVersion", 2),
                JSONObject(valid.toString())
                    .put("verifiedProfile", JSONObject().put("id", UUID.randomUUID())),
                JSONObject(valid.toString()).apply {
                    getJSONObject("candidate").put("userID", "user_other_fixture")
                },
                JSONObject(valid.toString()).apply {
                    IdentityAuthority.VIPI_PRODUCTION.tag(getJSONObject("candidate"))
                },
            )
        for (record in invalid) assertTrue(
            runCatching { IdentityLinkJournal.parse(record) }.isFailure
        )
    }

    private fun profileCacheKey(subject: String) =
        "profile-" +
            java.security.MessageDigest.getInstance("SHA-256")
                .digest(subject.toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it) }

    private fun flowResult(subject: String, access: String = "synthetic-access") =
        JSONObject()
            .put("user", JSONObject().put("id", subject))
            .put("access_token", access)
            .put("refresh_token", "synthetic-refresh")

    private fun flowCallback(pending: JSONObject, cancelled: Boolean = false): Uri =
        Uri.Builder()
            .scheme("co.fallsoft.vipi")
            .authority("auth")
            .path("/callback")
            .appendQueryParameter("state", pending.getString("state"))
            .appendQueryParameter(
                if (cancelled) "error" else "code",
                if (cancelled) "access_denied" else "synthetic-code",
            )
            .build()

    private fun withLegacyFlow(
        action:
            (android.content.Context, PrivateRecords, Authentication, IdentityLinkIntent) -> Unit
    ) {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "ordered-identity-link-${UUID.randomUUID()}")
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        val records = PrivateRecords(context)
        val intent =
            IdentityLinkIntent(
                UUID.randomUUID().toString(),
                UUID.randomUUID().toString(),
                "user_original_fixture",
                UUID.randomUUID().toString(),
                "a".repeat(43),
            )
        records.write(
            "session",
            IdentityAuthority.VIPI_PRODUCTION.tag(
                JSONObject()
                    .put("userID", intent.oldUserID)
                    .put("accessToken", "synthetic-old-access")
                    .put("refreshToken", "synthetic-old-refresh")
            ),
        )
        records.write(
            profileCacheKey(intent.oldUserID),
            JSONObject()
                .put("id", intent.accountID)
                .put("username", "original_profile")
                .put("display_name", "Synthetic"),
        )
        val auth = Authentication(context)
        auth.qualificationExchange = {
            fail("Unexpected external exchange")
            throw java.io.IOException()
        }
        auth.qualificationLinkRequest = { _, _, _, _, _ ->
            fail("Unexpected backend request")
            throw java.io.IOException()
        }
        try {
            action(context, records, auth, intent)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun settingsActionObtainsFreshLegacyProofBeforeSharedReceiptAndPreservesAccountDeviceRequest() =
        withLegacyFlow { context, records, auth, fixture ->
            var launches = 0
            var posts = 0
            auth.qualificationSignInLaunch = { uri ->
                launches++
                assertEquals("0", uri.getQueryParameter("max_age"))
            }
            auth.qualificationExchange = { fields ->
                assertFalse(fields.has("client_secret"))
                when (fields.getString("client_id")) {
                    IdentityAuthority.VIPI_PRODUCTION.clientID ->
                        flowResult(fixture.oldUserID, "synthetic-fresh-legacy-access")
                    IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.clientID ->
                        flowResult("user_shared_fixture", "synthetic-shared-access")
                    else -> error("Wrong pinned client")
                }
            }
            runBlocking {
                withContext(Dispatchers.Main) {
                    assertTrue(auth.canLinkFallsoft)
                    auth.beginFallsoftLink(
                        context,
                        UUID.fromString(fixture.accountID),
                        DeviceCredential(UUID.fromString(fixture.deviceID), fixture.deviceSecret),
                    )
                    val source = requireNotNull(records.read("pending-sign-in"))
                    val bound = IdentityLinkIntent.parse(source.getJSONObject("sourceLink"))
                    assertEquals(IdentityAuthority.VIPI_PRODUCTION, IdentityAuthority.read(source))
                    assertEquals(fixture.oldUserID, source.getString("expectedUser"))
                    assertEquals(fixture.accountID, bound.accountID)
                    assertEquals(fixture.deviceID, bound.deviceID)
                    assertEquals(fixture.deviceSecret, bound.deviceSecret)
                    assertEquals(
                        "synthetic-old-access",
                        records.read("session")!!.getString("accessToken"),
                    )
                    auth.complete(flowCallback(source))
                    assertNotNull(records.read(profileCacheKey(fixture.oldUserID)))
                    val target = requireNotNull(records.read("pending-sign-in"))
                    val targetIntent = IdentityLinkIntent.parse(target.getJSONObject("link"))
                    assertEquals(2, launches)
                    assertFalse(target.has("sourceLink"))
                    assertEquals(bound, targetIntent)
                    assertEquals(
                        IdentityAuthority.FALLSOFT_VIPI_PRODUCTION,
                        IdentityAuthority.read(target),
                    )
                    assertEquals(fixture.oldUserID, auth.userID)
                    auth.qualificationLinkRequest = { method, _, body, token, device ->
                        assertEquals(fixture.deviceID, device.id.toString())
                        assertEquals(fixture.deviceSecret, device.secret)
                        if (method == "POST") {
                            posts++
                            assertEquals("synthetic-fresh-legacy-access", token)
                            assertEquals(bound.requestID, body!!.getString("request_id"))
                            assertEquals(bound.accountID, body.getString("expected_account_id"))
                            JSONObject()
                                .put("request_id", bound.requestID)
                                .put("account_id", bound.accountID)
                                .put(
                                    "authority_id",
                                    IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.recordID,
                                )
                                .put("authentication_subject", "user_shared_fixture")
                                .put("binding_revision", 1)
                        } else {
                            assertEquals("synthetic-shared-access", token)
                            JSONObject()
                                .put("id", bound.accountID)
                                .put("username", "original_profile")
                                .put("display_name", "Synthetic")
                        }
                    }
                    auth.complete(flowCallback(target))
                    assertEquals(1, posts)
                    assertNull(auth.error)
                    assertEquals("user_shared_fixture", auth.userID)
                    assertFalse(auth.canLinkFallsoft)
                    assertNull(records.read(profileCacheKey(fixture.oldUserID)))
                    assertEquals(
                        fixture.accountID,
                        records.read(profileCacheKey("user_shared_fixture"))!!.getString("id"),
                    )
                    assertEquals(
                        IdentityAuthority.FALLSOFT_VIPI_PRODUCTION,
                        IdentityAuthority.read(records.read("session")!!),
                    )
                }
            }
        }

    @Test
    fun wrongLegacyUserCannotContinueOrReplaceSession() =
        withLegacyFlow { context, records, auth, fixture ->
            var launches = 0
            auth.qualificationSignInLaunch = { launches++ }
            auth.qualificationExchange = { flowResult("user_wrong_fixture") }
            val original = records.read("session")!!.toString()
            runBlocking {
                withContext(Dispatchers.Main) {
                    auth.beginFallsoftLink(
                        context,
                        UUID.fromString(fixture.accountID),
                        DeviceCredential(UUID.fromString(fixture.deviceID), fixture.deviceSecret),
                    )
                    auth.complete(flowCallback(records.read("pending-sign-in")!!))
                    assertEquals(1, launches)
                    assertNotNull(auth.error)
                    assertEquals(original, records.read("session")!!.toString())
                    assertNotNull(records.read(profileCacheKey(fixture.oldUserID)))
                    assertNull(records.read("pending-identity-link"))
                }
            }
        }

    @Test
    fun cancellationAtEitherStageRetainsLegacyAndNeverLinks() {
        for (target in listOf(false, true)) withLegacyFlow { context, records, auth, fixture ->
            var launches = 0
            auth.qualificationSignInLaunch = { launches++ }
            auth.qualificationExchange = { flowResult(fixture.oldUserID, "synthetic-fresh-access") }
            runBlocking {
                withContext(Dispatchers.Main) {
                    auth.beginFallsoftLink(
                        context,
                        UUID.fromString(fixture.accountID),
                        DeviceCredential(UUID.fromString(fixture.deviceID), fixture.deviceSecret),
                    )
                    if (target) auth.complete(flowCallback(records.read("pending-sign-in")!!))
                    auth.complete(flowCallback(records.read("pending-sign-in")!!, cancelled = true))
                    assertEquals(if (target) 2 else 1, launches)
                    assertEquals(fixture.oldUserID, auth.userID)
                    assertTrue(auth.canLinkFallsoft)
                    assertNotNull(records.read(profileCacheKey(fixture.oldUserID)))
                    assertNull(records.read("pending-sign-in"))
                    assertNull(records.read("pending-identity-link"))
                    assertFalse(auth.busy)
                }
            }
        }
    }

    @Test
    fun recoveredJournalPinsOriginalRequestAndRejectsDifferentSharedUser() =
        withLegacyFlow { context, records, auth, fixture ->
            val candidate =
                IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(
                    JSONObject()
                        .put("userID", "user_shared_fixture")
                        .put("accessToken", "synthetic-shared-access")
                        .put("refreshToken", "synthetic-refresh")
                )
            records.write("pending-identity-link", IdentityLinkJournal(fixture, candidate).json())
            auth.qualificationSignInLaunch = {}
            auth.qualificationExchange = { fields ->
                flowResult(
                    if (fields.getString("client_id") == IdentityAuthority.VIPI_PRODUCTION.clientID)
                        fixture.oldUserID
                    else "user_wrong_fixture"
                )
            }
            runBlocking {
                withContext(Dispatchers.Main) {
                    auth.beginFallsoftLink(
                        context,
                        UUID.fromString(fixture.accountID),
                        DeviceCredential(UUID.fromString(fixture.deviceID), fixture.deviceSecret),
                    )
                    assertEquals(
                        fixture.requestID,
                        records
                            .read("pending-sign-in")!!
                            .getJSONObject("sourceLink")
                            .getString("requestID"),
                    )
                    auth.complete(flowCallback(records.read("pending-sign-in")!!))
                    assertEquals(
                        "user_shared_fixture",
                        records
                            .read("pending-sign-in")!!
                            .getJSONObject("link")
                            .getString("expectedSharedUser"),
                    )
                    auth.complete(flowCallback(records.read("pending-sign-in")!!))
                    assertEquals(fixture.oldUserID, auth.userID)
                    assertNotNull(auth.error)
                    assertNotNull(records.read(profileCacheKey(fixture.oldUserID)))
                    assertEquals(
                        "user_shared_fixture",
                        IdentityLinkJournal.parse(records.read("pending-identity-link")!!)
                            .candidate
                            .getString("userID"),
                    )
                }
            }
        }

    @Test
    fun sharedAndStagingSessionsHideAndCannotStartLegacyAction() =
        withLegacyFlow { context, records, _, fixture ->
            for (authority in
                listOf(
                    IdentityAuthority.FALLSOFT_VIPI_PRODUCTION,
                    IdentityAuthority.VIPI_STAGING,
                )) {
                records.write(
                    "session",
                    authority.tag(
                        JSONObject()
                            .put("userID", "user_shared_fixture")
                            .put("accessToken", "synthetic-access")
                            .put("refreshToken", "synthetic-refresh")
                    ),
                )
                val auth = Authentication(context)
                auth.qualificationSignInLaunch = {
                    fail("Only legacy accounts may launch this action")
                }
                assertFalse(auth.canLinkFallsoft)
                auth.beginFallsoftLink(
                    context,
                    UUID.fromString(fixture.accountID),
                    DeviceCredential(UUID.fromString(fixture.deviceID), fixture.deviceSecret),
                )
                assertNotNull(auth.error)
            }
        }

    @Test
    fun verifiedActivationRecoveryRemovesOnlyObsoleteLegacyCache() =
        withLegacyFlow { context, records, _, fixture ->
            val profile =
                JSONObject()
                    .put("id", fixture.accountID)
                    .put("username", "original_profile")
                    .put("display_name", "Synthetic")
            val candidate =
                IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(
                    JSONObject()
                        .put("userID", "user_shared_fixture")
                        .put("accessToken", "synthetic-shared-access")
                        .put("refreshToken", "synthetic-refresh")
                )
            records.write("session", candidate)
            records.write(profileCacheKey("user_shared_fixture"), profile)
            records.write(
                "pending-identity-link",
                IdentityLinkJournal(fixture, candidate, profile).json(),
            )
            val auth = Authentication(context)
            auth.qualificationLinkRequest = { _, _, _, _, _ ->
                fail("Verified activation recovery must not call backend")
                throw java.io.IOException()
            }
            runBlocking { withContext(Dispatchers.Main) { auth.resumeFallsoftLink() } }
            assertNull(auth.error)
            assertNull(records.read(profileCacheKey(fixture.oldUserID)))
            assertEquals(
                fixture.accountID,
                records.read(profileCacheKey("user_shared_fixture"))!!.getString("id"),
            )
            assertNull(records.read("pending-identity-link"))
        }

    @Test
    fun equalRawSubjectsAcrossRealmsDoNotEraseCurrentSharedProfile() =
        withLegacyFlow { context, records, _, fixture ->
            val profile = records.read(profileCacheKey(fixture.oldUserID))!!
            val candidate =
                IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(
                    JSONObject()
                        .put("userID", fixture.oldUserID)
                        .put("accessToken", "synthetic-shared-access")
                        .put("refreshToken", "synthetic-refresh")
                )
            records.write("session", candidate)
            records.write(
                "pending-identity-link",
                IdentityLinkJournal(fixture, candidate, profile).json(),
            )
            val auth = Authentication(context)
            auth.qualificationLinkRequest = { _, _, _, _, _ ->
                fail("Verified recovery must remain local")
                throw java.io.IOException()
            }
            runBlocking { withContext(Dispatchers.Main) { auth.resumeFallsoftLink() } }
            assertNull(auth.error)
            assertEquals(
                fixture.accountID,
                records.read(profileCacheKey(fixture.oldUserID))!!.getString("id"),
            )
        }
}
