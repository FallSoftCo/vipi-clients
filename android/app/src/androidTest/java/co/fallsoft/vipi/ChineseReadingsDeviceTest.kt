package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/** Self-contained regressions against the actual packaged marked data.
 * Historical tone-free replay receipts remain in QA; they are not tone acceptance. */
class ChineseReadingsDeviceTest {
    @Test fun markedContextualReadingsPreserveNeutralTonesUmlautsAndLiterals() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val reader = ChineseReadings(context.assets.open("readings/chinese-ordinary.json").use { it.readBytes() })
        val cases = listOf(
            "音乐" to "yīnyuè", "音樂" to "yīnyuè", "银行" to "yínháng", "銀行" to "yínháng",
            "重庆" to "Chóngqìng", "重慶" to "Chóngqìng",
            "银行行长" to "yínháng hángzhǎng", "銀行行長" to "yínháng hángzhǎng",
            "重复" to "chóngfù", "重複" to "chóngfù", "睡觉" to "shuìjiào", "睡覺" to "shuìjiào",
            "妈妈" to "māma", "媽媽" to "māma", "孩子" to "háizi", "什么" to "shénme", "什麼" to "shénme",
            "女儿" to "nǚ'ér", "女兒" to "nǚ'ér", "绿色" to "lǜsè", "綠色" to "lǜsè",
            "旅游" to "lǚyóu", "旅遊" to "lǚyóu", "牛奶" to "niúnǎi",
            "音乐，银行！重庆？" to "yīnyuè，yínháng！Chóngqìng？",
            "José 银行 café" to "José yínháng café", "m\u030c银行" to "m\u030c yínháng", "nǐ hǎo 银行" to "nǐ hǎo yínháng",
            "https://例子.cn/银行 音乐" to "https://例子.cn/银行 yīnyuè",
            "`银行` 音乐" to "`银行` yīnyuè", "了" to "liǎo", "々" to "tóng"
        )
        val rows = JSONArray()
        for ((source, expected) in cases) {
            val result = reader.resolve(source)
            assertEquals(source, expected, result.reading)
            assertEquals(source, result.pieces.joinToString("") { it.source })
            assertTrue(result.pieces.filter { it.protected }.all { it.source == it.reading && !it.converted })
            assertEquals(result, reader.resolve(source))
            rows.put(JSONObject().put("source", source).put("reading", result.reading))
        }
        assertNull(reader.resolve("音乐𠮷").reading)
        assertNull(reader.resolve("مرحبا").reading)
        readingRegressionFile(context, "chinese-marked-readings-native.json").writeText(JSONObject()
            .put("data_sha256", ChineseReadings.DATA_SHA256).put("cases", rows).put("passed", true).toString(2))
    }

    /** Deferred size qualification: intentionally excluded from the short/4K
     * packet. Preserve the old complete-boundary assertions and test the new
     * admission boundary only when the larger stage is explicitly selected. */
    @Test fun legacySizeBoundaryAndNewEnvelopeRemainComplete() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val reader = ChineseReadings(context.assets.open("readings/chinese-ordinary.json").use { it.readBytes() })
        val long = "银行还款。".repeat(3276) + "银行还款"
        assertEquals(16384, long.length)
        assertTrue(reader.resolve(long).reading!!.startsWith("yínháng"))
        assertNotNull(reader.resolve("银".repeat(16385)).reading)
        assertTrue(runCatching { reader.resolve("银".repeat(FullReadingLimits.MAX_TEXT_UTF16 + 1)) }
            .exceptionOrNull() is IllegalArgumentException)
    }

    @Test fun fullMessageReadingUsesLiveContextualPolyphones() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("yínháng hángzhǎng", FullMessageReadings.read(context, "银行行长", "zh").text)
        assertEquals("kāfēi", FullMessageReadings.read(context, "咖啡", "zh").text)
    }
}
