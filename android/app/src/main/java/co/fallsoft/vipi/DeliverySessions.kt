package co.fallsoft.vipi

import android.content.Context

/** Main-thread leases keep UI and background delivery on one protocol coordinator. */
internal object DeliverySessions {
    private data class Lease(val session: ChatSession, var owners: Int)

    private val sessions = mutableMapOf<String, Lease>()

    fun acquire(
        context: Context,
        authentication: Authentication,
        userID: String,
        transport: ChatTransport? = null,
    ): ChatSession {
        check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper())
        sessions[userID]?.let {
            it.owners++
            return it.session
        }
        return (if (transport == null)
                ChatSession(context.applicationContext, authentication, userID)
            else ChatSession(context.applicationContext, transport, userID))
            .also { sessions[userID] = Lease(it, 1) }
    }

    fun release(session: ChatSession) {
        check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper())
        val lease = sessions[session.userID] ?: return
        if (lease.session !== session) return
        if (--lease.owners == 0) {
            sessions.remove(session.userID)
            session.close()
        }
    }

    fun delete(session: ChatSession) {
        sessions.remove(session.userID)?.session?.close()
    }
}
