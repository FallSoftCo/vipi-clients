package co.fallsoft.vipi.core
import org.junit.Test
import org.junit.Assert.assertEquals
class SourceFrameLiteralRangesTest {
 @Test fun sameMatcherPreservesTrimmedUrlsRepeatedAndTechnicalLiterals() {
  val text="😀 @my dog, coffee_today.txt and https://example.org/a(b). @my"
  val ranges=TranslationIntegrity.protectedLiteralRanges(text)
  assertEquals(listOf("@my","coffee_today.txt","https://example.org/a(b)","@my"),ranges.map{text.substring(it)})
  assertEquals(ranges.map{text.substring(it)}.groupingBy{it}.eachCount(),TranslationIntegrity.identifiers(text))
  assertEquals(3,ranges.first().first)
 }
}
