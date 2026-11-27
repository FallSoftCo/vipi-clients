package co.fallsoft.vipi

import android.Manifest
import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.work.*
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONObject

class VipiApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.FIREBASE_CONFIGURED && FirebaseApp.getApps(this).isEmpty()) {
            FirebaseApp.initializeApp(
                this,
                FirebaseOptions.Builder()
                    .setApplicationId(BuildConfig.FIREBASE_APP_ID)
                    .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                    .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
                    .setApiKey(BuildConfig.FIREBASE_API_KEY)
                    .build(),
            )
        }
        getSystemService(NotificationManager::class.java)
            .createNotificationChannel(
                NotificationChannel(
                        PushDelivery.CHANNEL,
                        getString(R.string.ui_04d7b4833927),
                        NotificationManager.IMPORTANCE_DEFAULT,
                    )
                    .apply {
                        description = getString(R.string.ui_9648f84b6ea3)
                        lockscreenVisibility = android.app.Notification.VISIBILITY_PRIVATE
                    }
            )
    }
}

internal object PushDelivery {
    const val CHANNEL = "vipi_messages"
    const val ACTION = "co.fallsoft.vipi.OPEN_INBOX"
    private const val INBOX_WORK = "vipi-inbox"
    private const val REGISTER_WORK = "vipi-push-registration"
    private const val GROUP = "vipi-delivery"

    fun request(context: Context, registration: Boolean = false) {
        if (!BuildConfig.FIREBASE_CONFIGURED) return
        val request =
            OneTimeWorkRequestBuilder<InboxWorker>()
                .setInputData(workDataOf("registration" to registration))
                .setConstraints(
                    Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .addTag(GROUP)
                .build()
        // KEEP can lose a wakeup after an active worker's final inbox check.
        // Persist a successor instead; the relay coalesces pushes, while each
        // worker drains the inbox and the journal makes repeated drains safe.
        WorkManager.getInstance(context)
            .enqueueUniqueWork(
                if (registration) REGISTER_WORK else INBOX_WORK,
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                request,
            )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelAllWorkByTag(GROUP)
        clearPosted(context)
    }

    fun permissionGranted(context: Context) =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED

    fun allowed(context: Context) =
        permissionGranted(context) &&
            NotificationManagerCompat.from(context).areNotificationsEnabled() &&
            context
                .getSystemService(NotificationManager::class.java)
                .getNotificationChannel(CHANNEL)
                ?.importance != NotificationManager.IMPORTANCE_NONE

    private const val ALERT_ID = 1
    private const val TAG_PREFIX = "vipi-message-"

    internal data class Alert(
        val tag: String?,
        val notification: android.app.Notification,
        val deliveries: Map<UUID, String>,
    )

    private fun tag(account: String, peer: UUID): String =
        TAG_PREFIX + UUID.nameUUIDFromBytes("$account/$peer".toByteArray())

    private fun posted(context: Context) =
        context.getSystemService(NotificationManager::class.java).activeNotifications.filter {
            it.id == ALERT_ID && (it.tag == null || it.tag.startsWith(TAG_PREFIX))
        }

    fun clearPosted(context: Context) {
        val manager = NotificationManagerCompat.from(context)
        posted(context).forEach { manager.cancel(it.tag, it.id) }
    }

    fun clearPeer(context: Context, account: String, peer: UUID) {
        NotificationManagerCompat.from(context).cancel(tag(account, peer), ALERT_ID)
    }

    fun previewLine(text: String): String? {
        val line =
            text
                .replace(
                    Regex("[\\p{Cc}\\p{Z}\\u061C\\u200E\\u200F\\u202A-\\u202E\\u2066-\\u2069]+"),
                    " ",
                )
                .trim()
        if (line.isEmpty()) return null
        return if (line.codePointCount(0, line.length) <= 160) line
        else line.substring(0, line.offsetByCodePoints(0, 159)).trimEnd() + "…"
    }

    fun notify(context: Context, chat: ChatSession) {
        if (
            !allowed(context) ||
                ProcessLifecycleOwner.get()
                    .lifecycle
                    .currentState
                    .isAtLeast(Lifecycle.State.STARTED)
        )
            return
        val protectedStorageAvailable =
            context.getSystemService(android.os.UserManager::class.java).isUserUnlocked
        val alerts = buildNotifications(context, chat, protectedStorageAvailable)
        val manager = NotificationManagerCompat.from(context)
        val current = alerts.map { it.tag }.toSet()
        posted(context).filter { it.tag !in current }.forEach { manager.cancel(it.tag, it.id) }
        // Empty deliveries describe the desired shade state but have already
        // been posted. A duplicate wake or a new peer must respect dismissal.
        try {
            for (alert in alerts) if (alert.deliveries.isNotEmpty()) {
                manager.notify(alert.tag, ALERT_ID, alert.notification)
                chat.notificationPosted(alert.deliveries)
            }
        } catch (_: SecurityException) {
            /* permission changed */
        }
    }

    internal fun buildNotifications(
        context: Context,
        chat: ChatSession,
        protectedStorageAvailable: Boolean,
    ): List<Alert> {
        if (!chat.ready || chat.needsReauthentication || chat.needsDeviceRecovery)
            return emptyList()
        val unread =
            chat.threads.filter {
                it.unread > 0 &&
                    it.peer !in chat.blockedPeers &&
                    it.peer !in chat.peersNeedingRecovery
            }
        if (unread.isEmpty()) return emptyList()
        fun build(
            peer: UUID?,
            sender: String? = null,
            body: String? = null,
        ): android.app.Notification {
            val intent =
                Intent(context, MainActivity::class.java)
                    .setAction(ACTION)
                    .setIdentifier(
                        peer?.let { tag(chat.userID, it) }
                            ?: "vipi-inbox-" + UUID.nameUUIDFromBytes(chat.userID.toByteArray())
                    )
                    .putExtra("notification_account", chat.userID)
                    .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            if (peer != null) intent.putExtra("notification_peer", peer.toString())
            val pending =
                PendingIntent.getActivity(
                    context,
                    ALERT_ID,
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
            val builder =
                NotificationCompat.Builder(context, CHANNEL)
                    .setSmallIcon(R.drawable.vipi_notification)
                    .setContentTitle(sender ?: context.getString(R.string.ui_0882ca640d5a))
                    .setContentText(body ?: context.getString(R.string.ui_3abeae7a3bed))
                    .setContentIntent(pending)
                    .setAutoCancel(true)
                    .setOnlyAlertOnce(true)
                    .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
                    .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            if (body != null && peer != null)
                builder
                    .setGroup(tag(chat.userID, peer))
                    .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                    .setPublicVersion(build(null))
            return builder.build()
        }
        val alerts = mutableListOf<Alert>()
        val hidden = mutableListOf<UUID>()
        val hiddenDeliveries = mutableMapOf<UUID, String>()
        for (thread in unread) {
            val peer = thread.peer
            val name =
                chat.contacts[peer]?.let { previewLine(it.displayName) ?: previewLine(it.username) }
            val receipt =
                runCatching { chat.notificationDelivery(peer, protectedStorageAvailable) }
                    .getOrNull() ?: continue
            val body = if (name != null) receipt.preview else null
            val newDelivery = if (receipt.pending) mapOf(peer to receipt.id) else emptyMap()
            if (body != null)
                alerts += Alert(tag(chat.userID, peer), build(peer, name, body), newDelivery)
            else {
                hidden += peer
                hiddenDeliveries.putAll(newDelivery)
            }
        }
        if (hidden.isNotEmpty())
            alerts += Alert(null, build(hidden.singleOrNull()), hiddenDeliveries)
        return alerts
    }
}

class VipiMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        PushDelivery.request(this, registration = true)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        if (message.data == mapOf("kind" to "inbox_changed")) PushDelivery.request(this)
    }

    override fun onDeletedMessages() {
        PushDelivery.request(this)
    }
}

class InboxWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result =
        withContext(Dispatchers.Main.immediate) {
            if (!BuildConfig.FIREBASE_CONFIGURED) return@withContext Result.success()
            val auth = Authentication(applicationContext)
            val user = auth.userID ?: return@withContext Result.success()
            if (
                runCatching { PrivateDeletionStore(applicationContext).load() }
                    .getOrElse {
                        return@withContext Result.failure()
                    } != null
            )
                return@withContext Result.success()
            var chat: ChatSession? = null
            try {
                withTimeout(90_000) {
                    chat = DeliverySessions.acquire(applicationContext, auth, user)
                    val active = requireNotNull(chat)
                    // Push must never register a replacement phone or create a profile.
                    if (!active.ready) return@withTimeout
                    if (inputData.getBoolean("registration", false)) {
                        val messaging = FirebaseMessaging.getInstance()
                        messaging.isAutoInitEnabled = true
                        val token = messaging.token.await()
                        active.registerPush(token)
                    } else {
                        active.checkInboxProtocol()
                        active.synchronize()
                        if (
                            auth.isCurrentAccount(user) &&
                                PrivateDeletionStore(applicationContext).load() == null
                        ) {
                            PushDelivery.notify(applicationContext, active)
                        }
                        if (!active.lastSyncComplete)
                            throw java.io.IOException("Delivery incomplete")
                    }
                }
                Result.success()
            } catch (_: TimeoutCancellationException) {
                if (runAttemptCount < 3) Result.retry() else Result.failure()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                if (runAttemptCount < 3) Result.retry() else Result.failure()
            } finally {
                chat?.let(DeliverySessions::release)
            }
        }
}
