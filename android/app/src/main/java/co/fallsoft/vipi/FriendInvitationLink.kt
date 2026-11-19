package co.fallsoft.vipi

import java.net.URI
import java.util.Locale

/** An invitation selects a search, never signs in, sends a message, or trusts a peer. */
internal object FriendInvitationLink {
    private val names = Regex("[a-z][a-z0-9_]{2,23}")
    private val reserved = setOf("vipi", "vbot", "bot", "admin", "administrator", "support", "security", "fallsoft", "mambovipi", "system")

    fun username(value: String): String? = runCatching {
        if (value.length > 160) return null
        val uri = URI(value)
        if (uri.rawUserInfo != null || uri.port != -1 || uri.rawQuery != null || uri.rawFragment != null) return null
        val prefix = when {
            uri.scheme.equals("https", ignoreCase = true) && uri.host.equals("api.mambovipi.app", ignoreCase = true) -> "/invite/"
            uri.scheme.equals("co.fallsoft.vipi", ignoreCase = true) && uri.host.equals("invite", ignoreCase = true) -> "/"
            else -> return null
        }
        val path = uri.rawPath ?: return null
        if (!path.startsWith(prefix)) return null
        val name = path.removePrefix(prefix).lowercase(Locale.ROOT)
        name.takeIf { names.matches(it) && it !in reserved }
    }.getOrNull()
}
