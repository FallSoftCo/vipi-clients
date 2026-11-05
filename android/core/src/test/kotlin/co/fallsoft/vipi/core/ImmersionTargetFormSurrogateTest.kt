package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** Explicit target forms must not manufacture malformed UTF16 display text. */
class ImmersionTargetFormSurrogateTest {
    @Test fun targetFormFocusCannotTakeEitherHalfOfASurrogatePair() {
        val translation = "\uD83D\uDE42"
        fun align(start: Int, end: Int): ImmersionResult {
            val target = translation.substring(start, end)
            val entry = VocabularyEntry(
                "smile", listOf(target), sourceScope = VocabularySourceScope("smile", 0, 5),
                targetForms = listOf(VocabularyTargetForm(translation, target, start, end))
            )
            return ImmersionEngine().align(
                "smile", translation, listOf(entry), 1.0, "es", setOf(0, 5), setOf(0, 2), 1
            )
        }
        val intact = align(0, 2)
        assertEquals(1, intact.spans.size)
        assertEquals(translation, intact.spans.single().translated)
        for ((start, end) in listOf(0 to 1, 1 to 2)) {
            val split = align(start, end)
            assertEquals("smile", split.original)
            assertTrue("target form $start..$end splits a surrogate pair", split.spans.isEmpty())
            assertEquals("smile", ImmersionText.project(split))
        }
    }
}
