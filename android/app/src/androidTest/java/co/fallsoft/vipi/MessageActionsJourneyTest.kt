package co.fallsoft.vipi

import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.Until
import org.junit.Test
import java.util.UUID

/** Regular MainActivity + durable synthetic account. The paired relay test covers actual transport. */
class MessageActionsJourneyTest {
    @Test fun composeReplyThenOpenEmbeddedPreviewAndReactionControls() {
        val service = JourneyServices(false, accountDisplayName = "Alex", peerDisplayName = "Maya", translationFactory = {
            object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String) = when (text) {
                    "Coffee by the station?" -> "¿Café cerca de la estación?"
                    "Let's meet here: https://example.com/" -> "Nos vemos aquí: https://example.com/"
                    else -> text
                }
                override fun close() = Unit
            }
        })
        val original = UUID.randomUUID()
        val featureRow = UUID.randomUUID()
        val device = UUID.randomUUID()
        val url = "https://example.com/"
        val originalBody = "Coffee by the station?"
        val msg = "Let's meet here: $url"
        MainActivityJourneyFixture("message-actions", { app ->
            MessageVault(app, service.account).use { vault ->
                ConversationHistory(vault)
                HoldEducation(vault).dismiss()
                vault.transaction {
                    vault.put("contact", service.peer.toString(), ChatProfile(service.peer, "maya", "Maya").json().toString().toByteArray())
                    val now = System.currentTimeMillis()-10_000
                    fun row(id: UUID, text: String, out: Boolean, time: Long, features: ChatFeatures) {
                        val sender = if (out) service.account else service.peer
                        val e = ChatEnvelope(id, sender, if (out) service.peer else service.account, time, 2, ByteArray(64))
                        val kind = if (out) "outgoing" else "incoming"
                        vault.put(kind, id.toString(), StoredChat(e, text, "delivered", true, features = features).encode())
                        ConversationHistory.record(vault, kind, id, service.peer, time)
                    }
                    row(original, originalBody, true, now, ChatFeatures.EMPTY)
                    row(featureRow, msg, false, now + 1000, ChatFeatures(
                        MessageQuote(original, service.account, "text", originalBody), LinkSnapshot(url, "Saturday coffee • Station Café")))
                    ConversationReactions(vault).record(ConversationRef.Direct(service.peer),
                        MessageReaction(original, service.account, 1, "❤️"), service.peer, device, UUID.randomUUID())
                }
                service.generatedPeerReplies[featureRow] = msg
            }
            service.model(app)
        }).use { f ->
            f.instrumentation.runOnMainSync {
                f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES)
                f.model.changeConversationAnimation(false)
            }
            f.launch()
            fun node(selector: BySelector) = requireNotNull(f.device.wait(Until.findObject(selector), 16_000)) {
                "Missing native control: $selector"
            }
            fun capture(name: String) {
                f.instrumentation.waitForIdleSync()
                android.os.SystemClock.sleep(350)
                f.capture(name)
            }
            node(By.text("Maya")).click()
            node(By.text("Saturday coffee • Station Café"))
            val originalView = By.descStartsWith("¿Café cerca de la estación?.")
            val incomingView = By.descStartsWith("Nos vemos aquí:")
            node(originalView)
            node(incomingView)
            capture("01-reply-card-and-reaction")
            val rect = node(originalView).visibleBounds
            val start = android.os.SystemClock.uptimeMillis()
            fun pointer(action: Int) {
                val event = android.view.MotionEvent.obtain(start, android.os.SystemClock.uptimeMillis(), action,
                    rect.exactCenterX(), rect.exactCenterY(), 0)
                event.source = android.view.InputDevice.SOURCE_TOUCHSCREEN
                try { check(f.instrumentation.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
            }
            pointer(android.view.MotionEvent.ACTION_DOWN)
            try {
                node(By.descStartsWith("$originalBody."))
                capture("01b-held-original")
            } finally { pointer(android.view.MotionEvent.ACTION_UP) }
            node(originalView)
            val editor = By.clazz("android.widget.EditText")
            node(editor).click()
            node(editor).text = "I'll be there."
            // Focus opens the real IME; wait for its animation and the transcript's follow-latest
            // remeasure before using screen coordinates. Keep the drag outside Android's back edge.
            capture("gesture-before-swipe")
            val from = node(incomingView).visibleBounds
            val density = f.base.resources.displayMetrics.density
            val startX = maxOf(from.left + 32 * density, from.centerX() - 32 * density)
            val endX = minOf(f.device.displayWidth - 32 * density, startX + 115 * density)
            require(endX - startX > 60 * density)
            val y = from.exactCenterY()
            val down = android.os.SystemClock.uptimeMillis()
            fun swipePoint(action: Int, x: Float) {
                val event = android.view.MotionEvent.obtain(down, android.os.SystemClock.uptimeMillis(), action, x, y, 0)
                event.source = android.view.InputDevice.SOURCE_TOUCHSCREEN
                try { check(f.instrumentation.uiAutomation.injectInputEvent(event, false)) } finally { event.recycle() }
            }
            swipePoint(android.view.MotionEvent.ACTION_DOWN, startX)
            try {
                for (step in 1..6) {
                    android.os.SystemClock.sleep(18)
                    swipePoint(android.view.MotionEvent.ACTION_MOVE, startX + (endX - startX) * step / 6f)
                }
            } finally { swipePoint(android.view.MotionEvent.ACTION_UP, endX) }
            java.io.File(f.output, "swipe.json").writeText(org.json.JSONObject().put("paragraph", from.toShortString())
                .put("x1", startX).put("x2", endX).put("y", y).put("duration_ms", android.os.SystemClock.uptimeMillis() - down).toString())
            capture("gesture-after-swipe")
            val close = By.desc(f.base.getString(R.string.message_remove_quote))
            node(close)
            check(node(editor).text == "I'll be there.")
            capture("02-swipe-reply-keeps-draft")
            node(close).click()
            check(node(editor).text == "I'll be there.")
            node(editor).text = ""
            val footer = By.desc(f.base.getString(R.string.message_actions))
            node(footer)
            f.device.findObjects(footer).maxBy { it.visibleCenter.y }.click()
            val more = By.text(f.base.getString(R.string.message_more_emoji))
            node(more)
            capture("03-message-action-menu")
            node(more).click()
            node(By.text(f.base.getString(R.string.message_any_emoji)))
        }
    }
}
