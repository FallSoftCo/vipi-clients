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
        val long = "银行还款。".repeat(3276) + "银行还款"
        assertEquals(16384, long.length)
        assertTrue(reader.resolve(long).reading!!.startsWith("yínháng"))
        assertTrue(runCatching { reader.resolve("银".repeat(16385)) }.exceptionOrNull() is IllegalArgumentException)
        File(context.filesDir, "chinese-marked-readings-native.json").writeText(JSONObject()
            .put("data_sha256", ChineseReadings.DATA_SHA256).put("cases", rows).put("passed", true).toString(2))
    }

    @Test fun exactOnboardingPreviewAndAuthoredSentenceKeepTonesAndChineseSpeech() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val result = ConversationExamples.result(context, "en", "zh")
        val preview = JSONObject(context.assets.open("immersion-preview.json").bufferedReader().use { it.readText() })
            .getJSONObject("languages").getJSONObject("zh")
        assertEquals("kāfēi", preview.getJSONObject("words").getJSONObject("coffee").getString("reading"))
        assertEquals("míngtiān", preview.getJSONObject("words").getJSONObject("tomorrow").getString("reading"))
        assertEquals("hé", preview.getJSONObject("words").getJSONObject("river").getString("reading"))
        assertEquals("Míngtiān yīqǐ hē kāfēi ma? Wǒ zhīdào hébiān yǒu ge xiǎo dìfang.", ConversationExamples.reading(context, "zh"))
        assertTrue(result.spans.isNotEmpty())
        assertTrue(result.spans.all { it.romanization in setOf("kāfēi", "míngtiān", "hé") })
        val chineseSpeech = result.speech("en", "zh").filter { it.language == "zh" }
        assertTrue(chineseSpeech.isNotEmpty())
        assertTrue(chineseSpeech.all { it.text in setOf("咖啡", "明天", "河") })
        val authored = SentenceReadings(context)
        val exact = NativeFullReadings.resolve("你好。", "zh", authored, context)
        assertEquals("Nǐ hǎo.", exact?.text)
        assertEquals(FullReading.Provenance.AUTHORED, exact?.provenance)
        assertEquals("yīnyuè", NativeFullReadings.resolve("音乐", "zh", authored, context)?.text)
        assertEquals(FullReading.Provenance.LOCAL_TRANSLITERATION,
            NativeFullReadings.resolve("音乐", "zh", authored, context)?.provenance)
    }
}
