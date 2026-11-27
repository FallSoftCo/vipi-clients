package co.fallsoft.vipi

import android.os.Bundle
import android.util.Base64
import androidx.test.platform.app.InstrumentationRegistry
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Read-only comparison; emits field names and equality, never decoded values. */
class ProfileSnapshotCompareDeviceTest {
    @Test
    fun compareRetainedEncryptedProfiles() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val name = requireNotNull(args.getString("profile_name"))
        require(name.matches(Regex("profile-[a-f0-9]{64}")))
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val key =
            store.getKey("co.fallsoft.vipi.private.v1", null) as? SecretKey
                ?: error("existing private record key missing")
        fun decode(field: String): JSONObject {
            val bytes = Base64.decode(requireNotNull(args.getString(field)), Base64.NO_WRAP)
            require(bytes.size in 30..65536 && bytes[0] == 1.toByte())
            val cipher =
                Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
                    updateAAD(name.toByteArray())
                }
            return JSONObject(
                cipher.doFinal(bytes.copyOfRange(13, bytes.size)).toString(Charsets.UTF_8)
            )
        }
        val before = decode("before_cipher")
        val after = decode("after_cipher")
        val fields =
            (before.keys().asSequence().toSet() + after.keys().asSequence().toSet()).sorted()
        require(fields.all { it.matches(Regex("[a-z_]{1,40}")) })
        val result = JSONObject()
        for (field in fields) result.put(
            field,
            before.has(field) &&
                after.has(field) &&
                JSONObject.wrap(before.get(field)) == JSONObject.wrap(after.get(field)),
        )
        val idEqual = result.optBoolean("id", false)
        val usernameEqual = result.optBoolean("username", false)
        inst.sendStatus(
            0,
            Bundle().apply {
                putString("profile_field_equality", result.toString())
                putBoolean("identity_equal", idEqual && usernameEqual)
                putBoolean("existing_key_available", true)
            },
        )
        assertTrue("profile id changed", idEqual)
        assertTrue("profile username changed", usernameEqual)
    }
}
