package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** New diagnostic fixture; does not replace the retained failing cafe/emoji controls. */
class ImmersionTargetFormNfcStableTest {
    @Test fun explicitTargetFormRequiresAWholeGraphemeInsideAnNfcStableCarrier() {
        // q+acute has no composed NFC equivalent; every code point is in the BMP.
        // Only whole carrier edges are supplied, so plain focus matching must miss.
        val carrier = "q\u0301s"
        fun align(focus: String, end: Int): ImmersionResult {
            val entry = VocabularyEntry(
                "letter", listOf(focus), sourceScope = VocabularySourceScope("letter", 0, 6),
                targetForms = listOf(VocabularyTargetForm(carrier, focus, 0, end))
            )
            return ImmersionEngine().align(
                "letter", carrier, listOf(entry), 1.0, "es", setOf(0, 6), setOf(0, 3), 1
            )
        }
        val intact = align("q\u0301", 2)
        assertEquals("explicit target-form prerequisite must actually produce a hit", 1, intact.spans.size)
        val span = intact.spans.single()
        assertEquals("q\u0301", span.translated)
        assertEquals(0, span.targetStart)
        assertEquals(2, span.targetEnd)
        assertEquals("letter", intact.original)
        assertEquals(carrier, intact.translation)
        assertEquals("letter", ImmersionText.project(intact, setOf(0)))

        val split = align("q", 1)
        assertTrue("focus before the combining mark is not a whole grapheme", split.spans.isEmpty())
        assertEquals("letter", split.original)
        assertEquals(carrier, split.translation)
        assertEquals("letter", ImmersionText.project(split))
    }
}
