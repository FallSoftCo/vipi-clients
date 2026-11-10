package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

/** Bounded detector parity and bridge safety, not a language accuracy benchmark. */
class CLD2DetectorDeviceTest {
    @Test fun nativeParityAndBounds() = runBlocking {
        val inst = InstrumentationRegistry.getInstrumentation()
        val rows = JSONArray(inst.context.assets.open("cld2-detector-parity.json").bufferedReader().use { it.readText() })
        MessageLanguage().use { detector ->
            for (i in 0 until rows.length()) {
                val row = rows.getJSONObject(i)
                val masked = MessageLanguage.mask(row.getString("text"))
                assertEquals(row.getString("id"), row.getString("masked"), masked)
                val actual = requireNotNull(LocalLanguageDetector.detect(masked.toByteArray(Charsets.UTF_8)))
                val expected = row.getJSONArray("native")
                assertEquals(expected.length(), actual.size)
                for (k in actual.indices) assertEquals(row.getString("id"), expected.getString(k), actual[k])
            }
            assertNull(detector.identify("a".repeat(16_385)))
            // An oversized protected literal must be rejected before masking can shrink it.
            assertNull(detector.identify("We will have coffee tomorrow. https://example.com/" + "x".repeat(16_384)))
            assertNull(detector.identify("abc"))
            assertNull(detector.identify("🙂"))
            assertNull(LocalLanguageDetector.detect(byteArrayOf()))
            assertNull(LocalLanguageDetector.detect(byteArrayOf(0xff.toByte())))
            assertNull(LocalLanguageDetector.detect(ByteArray(65_537) { 65 }))
            assertNotNull(LocalLanguageDetector.detect(ByteArray(65_536) { 65 }))
            detector.close()
            assertNull(detector.identify("We will have coffee tomorrow."))
        }
    }
}
