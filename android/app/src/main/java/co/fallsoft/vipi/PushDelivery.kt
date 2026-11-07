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
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

class VipiApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.FIREBASE_CONFIGURED && FirebaseApp.getApps(this).isEmpty()) {
            FirebaseApp.initializeApp(this, FirebaseOptions.Builder().setApplicationId(BuildConfig.FIREBASE_APP_ID)
                .setProjectId(BuildConfig.FIREBASE_PROJECT_ID).setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
                .setApiKey(BuildConfig.FIREBASE_API_KEY).build())
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(PushDelivery.CHANNEL, "Messages", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Private notifications when friends reply"
                lockscreenVisibility = android.app.Notification.VISIBILITY_PRIVATE
            })
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
        val request = OneTimeWorkRequestBuilder<InboxWorker>()
            .setInputData(workDataOf("registration" to registration))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST).addTag(GROUP).build()
        // KEEP can lose a wakeup after an active worker's final inbox check.
        // Persist a successor instead; the relay coalesces pushes, while each
        // worker drains the inbox and the journal makes repeated drains safe.
        WorkManager.getInstance(context).enqueueUniqueWork(if (registration) REGISTER_WORK else INBOX_WORK,
            ExistingWorkPolicy.APPEND_OR_REPLACE, request)
    }
    fun cancel(context: Context) { WorkManager.getInstance(context).cancelAllWorkByTag(GROUP); NotificationManagerCompat.from(context).cancel(1) }
    fun allowed(context: Context) = (Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) && NotificationManagerCompat.from(context).areNotificationsEnabled()
    fun notify(context: Context, chat: ChatSession) {
        if (!allowed(context) || ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return
        val unread = chat.threads.filter { it.unread > 0 }
        if (unread.isEmpty()) return
        val intent = Intent(context, MainActivity::class.java).setAction(ACTION).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (unread.size == 1) intent.putExtra("notification_peer", unread.single().peer.toString())
        val pending = PendingIntent.getActivity(context, 1, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, CHANNEL).setSmallIcon(R.drawable.vipi_notification)
            .setContentTitle("Vipi").setContentText("You have a new message.").setContentIntent(pending).setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setCategory(NotificationCompat.CATEGORY_MESSAGE).build()
        try { NotificationManagerCompat.from(context).notify(1, notification) } catch (_: SecurityException) { /* permission changed */ }
    }
}

class VipiMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) { PushDelivery.request(this, registration = true) }
    override fun onMessageReceived(message: RemoteMessage) {
        if (message.data == mapOf("kind" to "inbox_changed")) PushDelivery.request(this)
    }
    override fun onDeletedMessages() { PushDelivery.request(this) }
}

class InboxWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.Main.immediate) {
        if (!BuildConfig.FIREBASE_CONFIGURED) return@withContext Result.success()
        val auth = Authentication(applicationContext)
        val user = auth.userID ?: return@withContext Result.success()
        if (runCatching { PrivateDeletionStore(applicationContext).load() }.getOrElse { return@withContext Result.failure() } != null) return@withContext Result.success()
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
                    active.synchronize()
                    PushDelivery.notify(applicationContext, active)
                    if (!active.lastSyncComplete) throw java.io.IOException("Delivery incomplete")
                }
            }
            Result.success()
        } catch (_: TimeoutCancellationException) { if (runAttemptCount < 3) Result.retry() else Result.failure() }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { if (runAttemptCount < 3) Result.retry() else Result.failure() }
        finally { chat?.let(DeliverySessions::release) }
    }
}
