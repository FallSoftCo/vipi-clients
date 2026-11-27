package co.fallsoft.vipi

import android.content.Intent
import android.util.Base64
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * Opt-in hosted-browser proof. The operator enters the owned QA account's real credentials. This
 * does not inject a session, rotate keys or replace a device.
 */
class ReauthenticationDeviceTest {
    @Test
    fun hostedSignInAgainAdvancesAuthTimeWithoutReplacingDevice() = runBlocking {
        assumeTrue(
            InstrumentationRegistry.getArguments().getString("vipiLiveReauthentication") == "true"
        )
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val records = PrivateRecords(context)
        val original = requireNotNull(records.read("session"))
        val config = JSONObject(File(context.filesDir, "network-config.json").readText())
        require(config.getString("username") == "vqa_1107_android01")
        require(original.getString("userID") == config.getString("expected_subject"))
        fun claims(session: JSONObject): JSONObject {
            val payload = session.getString("accessToken").split('.')[1]
            return JSONObject(
                Base64.decode(payload, Base64.URL_SAFE or Base64.NO_WRAP).toString(Charsets.UTF_8)
            )
        }
        val before = claims(original).getLong("auth_time")
        val started = System.currentTimeMillis() / 1000
        require(started - before > 600) {
            "Existing session must be stale for recent-auth qualification"
        }
        val receipt =
            JSONObject()
                .put("started_at_epoch", started)
                .put("previous_auth_time", before)
                .put(
                    "flow",
                    "existing native Authentication.signIn(expectedUser), hosted public PKCE max_age=0",
                )
                .put("complete", false)
        val out = File(context.filesDir, "reauthentication-001.json")
        require(!out.exists())
        out.writeText(receipt.toString(2))
        // AuthKit's singleTask callback may replace the initially launched host.
        // Own only that original activity, rather than asking ActivityScenario
        // to destroy a now-replaced browser/callback task during teardown.
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val host =
            instrumentation.startActivitySync(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ) as MainActivity
        try {
            lateinit var model: VipiModel
            instrumentation.runOnMainSync { model = ViewModelProvider(host)[VipiModel::class.java] }
            val deadline = System.currentTimeMillis() + 180_000
            while (model.chat?.ready != true && System.currentTimeMillis() < deadline) Thread.sleep(
                200
            )
            val chat = requireNotNull(model.chat)
            val device = requireNotNull(chat.eventDevice())
            val account = requireNotNull(chat.profile).id
            instrumentation.runOnMainSync {
                model.authentication.signIn(host, expectedUser = original.getString("userID"))
            }
            var after: JSONObject? = null
            while (System.currentTimeMillis() < deadline) {
                val current = records.read("session")
                if (current != null && claims(current).getLong("auth_time") > before) {
                    after = current
                    break
                }
                Thread.sleep(250)
            }
            val updated =
                requireNotNull(after) {
                    "Fresh hosted sign-in did not complete within the observation window"
                }
            val authTime = claims(updated).getLong("auth_time")
            assertEquals(original.getString("userID"), updated.getString("userID"))
            assertTrue(authTime >= started - 5)
            assertTrue(System.currentTimeMillis() / 1000 - authTime < 600)
            val api = ServiceClient(model.authentication, updated.getString("userID"))
            assertEquals(account.toString(), api.request("GET", "/v1/me").getString("id"))
            // Re-register this exact already-active credential without replacement.
            // The live server enforces auth_time <= 10 min before this idempotent path.
            val confirmed =
                api.request(
                    "POST",
                    "/v1/devices",
                    JSONObject()
                        .put("device_id", device.id)
                        .put("secret", device.secret)
                        .put("replace_active", false),
                )
            assertEquals(device.id.toString(), confirmed.getString("id"))
            assertTrue(confirmed.getBoolean("active"))
            assertEquals(device, chat.eventDevice())
            receipt
                .put("complete", true)
                .put("new_auth_time", authTime)
                .put("finished_at_epoch", System.currentTimeMillis() / 1000)
                .put("same_subject", true)
                .put("same_account", true)
                .put("same_device", true)
                .put(
                    "live_recent_auth_device_registration",
                    "accepted; replace_active=false; existing credential",
                )
            out.writeText(receipt.toString(2))
        } finally {
            instrumentation.runOnMainSync { if (!host.isDestroyed) host.finish() }
        }
    }
}
