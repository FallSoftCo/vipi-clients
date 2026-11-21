package co.fallsoft.vipi

import android.os.ParcelFileDescriptor
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CompletableDeferred
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.io.FileNotFoundException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import kotlin.math.sin

class InlineVoicePlaybackDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun retriesOnTapAndCancelsAnOlderPendingNote() {
        val app = InstrumentationRegistry.getInstrumentation().targetContext
        val path = File(app.cacheDir, "inline-player-${UUID.randomUUID()}.wav")
        val rate = 8_000
        val count = rate * 5
        val data = ByteBuffer.allocate(44 + count * 2).order(ByteOrder.LITTLE_ENDIAN)
        data.put("RIFF".toByteArray()).putInt(36 + count * 2).put("WAVEfmt ".toByteArray())
            .putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate * 2)
            .putShort(2).putShort(16).put("data".toByteArray()).putInt(count * 2)
        repeat(count) { data.putShort((sin(2 * Math.PI * 220 * it / rate) * 1800).toInt().toShort()) }
        path.writeBytes(data.array())
        fun open() = ParcelFileDescriptor.open(path, ParcelFileDescriptor.MODE_READ_ONLY)
        val firstStarted = CompletableDeferred<Unit>()
        val releaseFirst = CompletableDeferred<Unit>()
        var retries = 0
        val play = app.getString(R.string.media_open_voice)
        val pause = app.getString(R.string.media_pause)
        try {
            compose.setContent {
                MaterialTheme {
                    Column {
                        InlineVoicePlayer(5_000) { firstStarted.complete(Unit); releaseFirst.await(); open() }
                        InlineVoicePlayer(5_000) { if (retries++ == 0) throw FileNotFoundException(); open() }
                    }
                }
            }
            compose.onAllNodesWithContentDescription(play)[0].performClick()
            compose.waitUntil(3_000) { firstStarted.isCompleted }
            compose.onNodeWithContentDescription(play).performClick()
            compose.onNodeWithText(app.getString(R.string.media_open_error)).assertExists()
            releaseFirst.complete(Unit)
            compose.onNodeWithContentDescription(app.getString(R.string.try_again)).performClick()
            compose.waitUntil(6_000) { compose.onAllNodesWithContentDescription(pause).fetchSemanticsNodes().size == 1 }
            compose.waitUntil(6_000) { compose.onAllNodesWithText("0:01 / 0:05", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
                || compose.onAllNodesWithText("00:01 / 00:05", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithContentDescription(pause).performClick()
            compose.onAllNodesWithContentDescription(play).assertCountEquals(2)
            compose.runOnIdle { stopInlineVoicePlayback() }
            compose.onAllNodesWithContentDescription(play).assertCountEquals(2)
            check(retries == 2)
        } finally { releaseFirst.complete(Unit); path.delete() }
    }
}
