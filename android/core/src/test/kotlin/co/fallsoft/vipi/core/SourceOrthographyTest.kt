package co.fallsoft.vipi.core
import org.junit.Assert.*
import org.junit.Test

class SourceOrthographyTest {
 @Test fun nativeOrReviewedScopesCannotSeverArabicArticles() {
  for((text,a,b) in listOf(Triple("أنا أشرب الماء الآن.",11,14),Triple("أنا أحب الموسيقى.",10,16))) {
   val surface=text.substring(a,b)
   for(scoped in listOf(false,true)) {
    val entry=VocabularyEntry(surface,listOf("meaning"),sourceScope=if(scoped)VocabularySourceScope(text,a,b)else null)
    assertTrue(ImmersionEngine().align(text,"meaning",listOf(entry),1.0,"en",setOf(a,b),sourceTokenCount=8).spans.isEmpty())
   }
   assertNull(SourceReferencePresentation.create(text,"en",listOf(SourceReferenceUnit(a,b,surface,"meaning",null,"qa","a".repeat(64),1)),1.0,8))
  }
 }
 @Test fun fullArabicTokenSurvivesWithVowelsTatweelAndJoinControls() {
  for(text in listOf("الماء","الْمَاءُ","الـماء","ال\u200Dماء","ال\u200Cماء","ماءـ")) {
   assertTrue(text,SourceOrthography.permitsReplacement(text,0,text.length))
   assertFalse(text,SourceOrthography.permitsReplacement(text,0,text.length-1))
  }
  assertFalse(SourceOrthography.permitsReplacement("الـماء",0,2))
  assertFalse(SourceOrthography.permitsReplacement("الـماء",3,6))
 }
 @Test fun safeWholeWordAndOtherScriptsRemainAvailable() {
  val text="الماء كتاب"
  val units=listOf(SourceReferenceUnit(2,5,"ماء","water",null,"bad","a".repeat(64),1),SourceReferenceUnit(6,10,"كتاب","book",null,"good","a".repeat(64),1))
  val partial=requireNotNull(SourceReferencePresentation.create(text,"en",units,1.0,2))
  assertEquals(listOf("كتاب"),partial.spans.map{it.original})
  assertEquals(text,ImmersionText.project(partial,partial.spans.map{it.id}.toSet()))
  for((word,end) in listOf("books" to 4,"책을" to 1,"私は" to 1,"中国" to 1))assertTrue(SourceOrthography.permitsReplacement(word,0,end))
 }
}
