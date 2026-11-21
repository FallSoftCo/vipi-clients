package co.fallsoft.vipi

import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class PracticeVoiceLanguageTest {
    @Test fun mandarinMatchesTheDisplayedPinyin() {
        for (tag in listOf("cmn", "cmn-HK", "zh-cmn-Hans-CN", "zh-CN", "zh-Hans-SG", "zh-TW", "zh-Hant-TW")) {
            assertEquals(tag, "zh", practiceVoiceLanguage(Locale.forLanguageTag(tag)))
        }
        for (tag in listOf("zh", "zh-Hant", "zh-Hans", "zh-HK", "zh-Hant-HK", "zh-MO",
            "yue", "zh-yue-CN", "wuu-CN", "zh-gan-CN", "zh-CN-x-regional")) {
            assertNotEquals(tag, "zh", practiceVoiceLanguage(Locale.forLanguageTag(tag)))
        }
        assertEquals("es", practiceVoiceLanguage(Locale.forLanguageTag("es-MX")))
    }
}
