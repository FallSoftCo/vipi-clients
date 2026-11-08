package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test
import kotlin.coroutines.*

class SourceLookupEvidenceTest {
    private val text = "country music book"
    private val translated = "nchi muziki kitabu"
    private val identity = "catalog:revision1:known0"
    private val mask = SourceRecognition("country_music", "a".repeat(64), SourceLookupRange(0, 13),
        SourceLookupRange(0, 13), SourceAtomicMode.HEAD_BACKOFF, listOf(SourceApprovedOutput("music", SourceLookupRange(8, 13))))
    private fun evidence(partial: PartialImmersionResult? = null, rules: List<SourceRecognition> = listOf(mask)) =
        SourceLookupEvidence(text, "en", "sw", identity, partial, rules)
    private fun legacy() = ImmersionResult(text, translated, listOf(ImmersionSpan(0, 7, "country", "nchi", 0, 4),
        ImmersionSpan(8, 13, "music", "muziki", 5, 11), ImmersionSpan(14, 18, "book", "kitabu", 12, 18)))
    private fun partial(id: String? = "music") = requireNotNull(SourceReferencePresentation.create(text, "sw",
        listOf(SourceReferenceUnit(8, 13, "music", "muziki", null, "approved-record", "a".repeat(64), 1, id)), .50, 3))
    private fun <T> immediate(block: suspend () -> T): T {
        var result: Result<T>? = null
        block.startCoroutine(object : Continuation<T> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(value: Result<T>) { result = value }
        })
        return requireNotNull(result).getOrThrow()
    }
    private fun resolve(value: SourceLookupEvidence = evidence(), known: Boolean = false,
        ready: Boolean = true, events: MutableList<String> = mutableListOf(), valid: () -> Boolean = { true },
        evidenceHook: () -> Unit = {}, input: String? = "en", detected: String = "en"): LookupFirstOutcome = immediate {
        LookupFirst.resolve(LookupFirstRequest(text, "en", "sw", input), valid,
            reference = { _, from, _ -> events += "reference:$from"; if (known && from == "en") translated else null },
            identify = { detected }, modelsReady = { ready },
            translate = { _, _, _ -> events += "translate"; if (detected == "sw" || input == "sw") text else translated },
            align = { original, target, _ -> events += "align"; if (original == text && target == translated) legacy() else ImmersionResult(original, target, emptyList()) },
            sourceEvidenceIdentity = identity, sourceEvidence = { _, _, _ -> events += "evidence"; evidenceHook(); value })
    }
    @Test fun nilPartialStillProtectsScopesAndKeepsUnmaskedOutputAndCompleteReference() {
        val result = resolve()
        assertEquals(ImmersionStatus.READY, result.status)
        assertEquals(translated, result.result!!.translation)
        assertEquals(listOf("book"), result.result!!.spans.map { it.original })
        assertEquals(1, result.sourceEvidence!!.recognitions.size)
        assertEquals(1, result.localTranslationCalls)
    }
    @Test fun forwardWholeReferenceStillAcquiresIndependentRecognition() {
        val events = mutableListOf<String>(); val result = resolve(known = true, ready = false, events = events)
        assertEquals(listOf("reference:en", "evidence", "align"), events)
        assertEquals(listOf("book"), result.result!!.spans.map { it.original })
        assertEquals(0, result.localTranslationCalls)
    }
    @Test fun knownOrOverBudgetFaceAbsenceCannotEraseMetadataOnMissingModels() {
        val result = resolve(ready = false)
        assertNull(result.result); assertEquals(ImmersionStatus.MODEL_NOT_READY, result.status)
        assertEquals(mask, result.sourceEvidence!!.recognitions.single())
    }
    @Test fun approvedPartialNeedsExplicitIDAndExactGeometryNotTextEquality() {
        val rules = evidence()
        assertNotNull(rules.filterPartial(partial()))
        assertNull(rules.filterPartial(partial(null)))
        assertNull(rules.filterPartial(partial("some-other-record")))
        assertEquals(listOf("book"), rules.filterLegacy(legacy()).spans.map { it.original })
        val wrongScope = evidence(rules = listOf(mask.copy(approvedOutputs = listOf(SourceApprovedOutput("music", SourceLookupRange(0, 13))))))
        assertNull(wrongScope.filterPartial(partial()))
    }
    @Test fun everyOverlappingMaskAppliesEvenToAnOtherwiseApprovedHead() {
        val crossing = SourceRecognition("uncertain", "b".repeat(64), SourceLookupRange(8, 18), SourceLookupRange(8, 18),
            SourceAtomicMode.AMBIGUOUS, emptyList())
        val value = evidence(rules = listOf(mask, crossing))
        assertNull(value.filterPartial(partial())); assertTrue(value.filterLegacy(legacy()).spans.isEmpty())
    }
    @Test fun providerPartialReturnsWithoutModelsAndRetainsEvidence() {
        val events = mutableListOf<String>(); val result = resolve(evidence(partial()), ready = false, events = events)
        assertEquals(ImmersionStatus.PARTIAL, result.status); assertNull(result.result!!.translation)
        assertEquals(listOf("music"), result.result!!.spans.map { it.original })
        assertFalse("translate" in events); assertFalse("align" in events); assertNotNull(result.sourceEvidence)
    }
    @Test fun invalidSourcePairIdentityProvenanceAndGraphemeRangesFailBeforeFallback() {
        val values = listOf(
            SourceLookupEvidence("changed", "en", "sw", identity, null, listOf(mask)),
            SourceLookupEvidence(text, "es", "sw", identity, null, listOf(mask)),
            SourceLookupEvidence(text, "en", "ja", identity, null, listOf(mask)),
            SourceLookupEvidence(text, "en", "sw", "different", null, listOf(mask)),
            evidence(rules = listOf(mask.copy(recordSHA256 = "invalid"))),
            evidence(rules = listOf(mask.copy(mask = SourceLookupRange(0, 30))))
        )
        for (value in values) {
            val events = mutableListOf<String>(); val result = resolve(value, events = events)
            assertEquals(ImmersionStatus.INVALID_RESULT, result.status); assertNull(result.result)
            assertFalse("translate" in events); assertFalse("align" in events)
        }
        val unicode = "a\u0301 😊"
        val bad = SourceRecognition("split", "c".repeat(64), SourceLookupRange(0, unicode.length),
            SourceLookupRange(0, 1), SourceAtomicMode.ATOMIC, emptyList())
        assertFalse(SourceLookupEvidence(unicode, "en", "sw", identity, null, listOf(bad)).isValid(unicode, "en", "sw", identity))
    }
    @Test fun reverseInputNeverInheritsOriginalForwardMasks() {
        val explicit = mutableListOf<String>(); val result = resolve(input = "sw", events = explicit)
        assertFalse("evidence" in explicit); assertNull(result.sourceEvidence)
        val automatic = resolve(input = null, detected = "sw")
        assertNull(automatic.sourceEvidence)
    }
    @Test fun staleProviderCompletionCannotPublishRecognitionOrPartial() {
        var valid = true; val events = mutableListOf<String>()
        val result = resolve(evidence(partial()), events = events, valid = { valid }, evidenceHook = { valid = false })
        assertEquals(ImmersionStatus.STALE, result.status); assertNull(result.result); assertNull(result.sourceEvidence)
        assertFalse("translate" in events)
    }
    @Test fun evidenceSnapshotsCallerOwnedCollections() {
        val approvals = mutableListOf(SourceApprovedOutput("music", SourceLookupRange(8, 13)))
        val rules = mutableListOf(mask.copy(approvedOutputs = approvals)); val value = evidence(rules = rules)
        approvals.clear(); rules.clear()
        assertNotNull(value.filterPartial(partial())); assertEquals(1, value.recognitions.size)
    }
    @Test fun sourceMasksFilterBeforeBudgetAndKeepSupplementalClaims() {
        val original = "country water"; val translated = "nchi maji"
        val guard = SourceRecognition("country", "a".repeat(64), SourceLookupRange(0, 7), SourceLookupRange(0, 7), SourceAtomicMode.ATOMIC, emptyList())
        val constraints = SourceLookupEvidence(original, "en", "sw", identity, null, listOf(guard))
        val country = VocabularyEntry("country", listOf("nchi"))
        val water = VocabularyEntry("water", listOf("maji"), sourceScope = VocabularySourceScope(original, 8, 13), targetScope = VocabularyTargetScope(translated, 5, 9))
        val baseline = ImmersionEngine().align(original, translated, listOf(country, water), .10, "sw")
        assertEquals(listOf("country"), baseline.spans.map { it.original })
        val result = ImmersionEngine().align(original, translated, listOf(country), .10, "sw", supplementalEntries = listOf(water), sourceEvidence = constraints)
        assertEquals(listOf("water"), result.spans.map { it.original }); assertEquals(translated, result.translation)
        val conflicting = VocabularyEntry("water", listOf("nchi"))
        val conflict = ImmersionEngine().align(original, translated, listOf(country, conflicting), .10, "sw", supplementalEntries = listOf(water), sourceEvidence = constraints)
        assertTrue("Blocked country's lexical claim still prevents conflicting target ownership", conflict.spans.isEmpty())
    }
}
