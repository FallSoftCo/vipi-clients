package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.core.ContextMappingMatcher
import co.fallsoft.vipi.core.VocabularyEntry
import co.fallsoft.vipi.core.VocabularySourceScope

/** Shared by authenticated downloads and app-signed bundled context data. */
internal object ReviewedContextLookup {
    fun entries(db: SQLiteDatabase, text: String, source: String, target: String): List<VocabularyEntry> {
        fun lookup(input:String):List<co.fallsoft.vipi.core.ContextMapping> {
            val mappings=mutableListOf<co.fallsoft.vipi.core.ContextMapping>()
            db.rawQuery("SELECT m.payload FROM context_inputs i JOIN mappings m ON m.id=i.mapping_id WHERE i.input=? ORDER BY m.id LIMIT 257",arrayOf(input)).use { cursor ->
                while (cursor.moveToNext()) {
                    mappings+=ReviewedContextRecord.mapping(cursor.getString(0),source,target)
                    require(mappings.size<=256)
                }
            }
            return mappings
        }
        val whole=lookup(text)
        // Never replace ambiguous whole-message evidence with a match
        // from a smaller context.
        if(whole.isNotEmpty())return ContextMappingMatcher.entries(text,source,target,whole)
        val entries=mutableListOf<VocabularyEntry>();var matched=0
        for(sentence in LocalImmersion.sentences(text,source).filter{it!=text.indices}) {
            val fragment=text.substring(sentence);val mappings=lookup(fragment);matched+=mappings.size
            if(matched>256)return emptyList()
            for(entry in ContextMappingMatcher.entries(fragment,source,target,mappings)) {
                val scope=requireNotNull(entry.sourceScope);require(scope.original==fragment)
                entries+=entry.copy(sourceScope=VocabularySourceScope(text,sentence.first+scope.start,sentence.first+scope.end))
            }
        }
        return entries
    }
}
