package co.fallsoft.vipi

import android.content.Context
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

/** Debug-only synthetic process termination probe. R8 removes its unused release path. */
internal object PersistenceProbe {
    private fun write(file: File, value: JSONObject) {
        val target = AtomicFile(file); val stream = target.startWrite()
        try { stream.write(value.toString().toByteArray()); target.finishWrite(stream) }
        catch (error: Exception) { target.failWrite(stream); throw error }
    }
    fun start(context: Context, action: String?) {
        if (!BuildConfig.DEBUG || action !in setOf("stage", "verify")) return
        val app = context.applicationContext
        Thread {
            val probe = File(app.filesDir, "storage-crash-probe.json")
            val armed = File(app.filesDir, "storage-crash-armed")
            val receipt = File(app.filesDir, "storage-crash-receipt.json")
            try {
                if (action == "stage") {
                    armed.delete(); receipt.delete()
                    val account = UUID.randomUUID()
                    write(probe, JSONObject().put("purpose", "SYNTHETIC SQLITE PROCESS TERMINATION").put("account", account.toString()))
                    MessageVault(app, account).use { vault ->
                        vault.transaction { vault.put("crash-test", "existing", "committed".toByteArray()) }
                        vault.transaction {
                            vault.put("crash-test", "existing", "uncommitted".toByteArray())
                            vault.put("crash-test", "new", "must roll back".toByteArray())
                            FileOutputStream(armed).use { it.write("armed".toByteArray()); it.fd.sync() }
                            Thread.sleep(60_000)
                            error("Process termination probe timed out")
                        }
                    }
                } else {
                    val values = JSONObject(probe.readText())
                    check(values.getString("purpose") == "SYNTHETIC SQLITE PROCESS TERMINATION")
                    MessageVault(app, UUID.fromString(values.getString("account"))).use { vault -> vault.transaction {
                        check(vault.get("crash-test", "existing")!!.toString(Charsets.UTF_8) == "committed")
                        check(vault.get("crash-test", "new") == null)
                    } }
                    write(receipt, JSONObject().put("status", "passed").put("account", values.getString("account")).put("scope", "abrupt process termination rolls back uncommitted native SQLite records"))
                }
            } catch (error: Exception) { write(receipt, JSONObject().put("status", "failed").put("error", error.javaClass.simpleName)) }
        }.start()
    }
}
