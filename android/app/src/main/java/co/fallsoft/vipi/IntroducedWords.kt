package co.fallsoft.vipi

import kotlinx.coroutines.sync.Mutex
import org.json.JSONObject
import java.lang.ref.WeakReference
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Indexed encrypted vocabulary, never a bundled dictionary or a count quota.
 * The index secret is itself encrypted in the account vault, so metadata IDs
 * cannot be guessed by hashing ordinary words. The preview has transient state. */
internal class IntroducedWords(private val vault: MessageVault?) : AutoCloseable {
    private val transient = mutableMapOf<String, IntroducedWord>()
    private val transientPlans = mutableMapOf<String, WordMessagePlan>()
    fun transientPlan(key: String) = transientPlans[key]
    fun commitTransientPlan(key: String, value: WordMessagePlan) { transientPlans.putIfAbsent(key, value) }
    private val indexKey = vault?.transaction {
        vault.get("word-index", "key-v1") ?: ByteArray(32).also {
            SecureRandom().nextBytes(it); vault.put("word-index", "key-v1", it)
        }
    }
    val progression: Mutex = if (vault == null) Mutex() else accountMutex(vault.account.toString())
    fun reference(source: String, target: String, key: String): String = opaque("introduced-word-v1", listOf(source, target, key).joinToString("\u0000"))
    fun planKey(id: String, text: String, source: String, target: String): String =
        opaque("word-message-plan-v1", listOf(id, WordMessagePlan.hash(text), source, target).joinToString("\u0000"))
    private fun opaque(scope: String, value: String): String {
        val plain = scope + "\u0000" + value
        val secret = indexKey ?: return plain
        return Mac.getInstance("HmacSHA256").run {
            init(SecretKeySpec(secret, "HmacSHA256"))
            doFinal(plain.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
        }
    }
    fun word(source: String, target: String, key: String): IntroducedWord? {
        val id = reference(source, target, key)
        val result = if (vault == null) transient[id] else vault.transaction {
            vault.get("introduced-word", id)?.let { IntroducedWord.parse(JSONObject(it.toString(Charsets.UTF_8))) }
        }
        return result?.also { require(it.source == source && it.target == target && it.key == key) }
    }
    fun referenced(id: String, source: String, target: String): IntroducedWord {
        val result = if (vault == null) transient[id] else vault.transaction {
            vault.get("introduced-word", id)?.let { IntroducedWord.parse(JSONObject(it.toString(Charsets.UTF_8))) }
        }
        return requireNotNull(result) { "Progression reference is missing" }.also {
            require(it.source == source && it.target == target && reference(source, target, it.key) == id)
        }
    }
    /** Called inside the SAME vault transaction as the immutable message plan.
     * Selection is serialized for this account, even across pair owners. */
    fun commit(word: IntroducedWord) {
        val id = reference(word.source, word.target, word.key)
        if (vault == null) { check(id !in transient); transient[id] = word }
        else {
            check(vault.get("introduced-word", id) == null) { "Introduced vocabulary is immutable" }
            vault.put("introduced-word", id, word.json().toString().toByteArray(Charsets.UTF_8))
        }
    }
    override fun close() { transient.clear(); transientPlans.clear(); indexKey?.fill(0) }
    companion object {
        private val mutexes = mutableMapOf<String, WeakReference<Mutex>>()
        @Synchronized private fun accountMutex(account: String): Mutex {
            mutexes.entries.removeAll { it.value.get() == null }
            return mutexes[account]?.get() ?: Mutex().also { mutexes[account] = WeakReference(it) }
        }
    }
}
