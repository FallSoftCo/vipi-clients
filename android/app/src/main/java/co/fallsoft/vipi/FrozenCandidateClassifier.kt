package co.fallsoft.vipi
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray

/** Original frozen classifier/family tables; never substitutes caller knowledge. */
internal class FrozenCandidateClassifier(db:SQLiteDatabase) {
    private val families=linkedMapOf<String,String>()
    private val roles=linkedMapOf<String,Set<String>>()
    private val functions=linkedSetOf<String>()
    init {
        db.rawQuery("SELECT source,family_id FROM known_families ORDER BY source",null).use{c->while(c.moveToNext()){val s=FrozenCandidateCatalog.text(c,0);val f=FrozenCandidateCatalog.text(c,1);require(s.isNotEmpty() && f.isNotEmpty() && s.toByteArray().size<=4096 && f.toByteArray().size<=4096 && s !in families && families.size<32768);families[s]=f}}
        db.rawQuery("SELECT source,roles_json FROM source_roles ORDER BY source",null).use{c->while(c.moveToNext()){val s=FrozenCandidateCatalog.text(c,0);val raw=FrozenCandidateCatalog.text(c,1);require(s.isNotEmpty() && s.toByteArray().size<=4096 && raw.toByteArray().size<=16384 && s !in roles && roles.size<32768);val a=JSONArray(raw);require(a.length()<=256);roles[s]=(0 until a.length()).map{a.getString(it).also{x->require(x.toByteArray().size<=4096)}}.toSet()}}
        db.rawQuery("SELECT source FROM function_words ORDER BY source",null).use{c->while(c.moveToNext()){val s=FrozenCandidateCatalog.text(c,0);require(s.isNotEmpty() && s.toByteArray().size<=4096 && functions.size<4096 && functions.add(s))}}
        require(families.size==3011 && roles.size==6384 && functions.size==87)
    }
    fun family(source:String):String?=families[source]
    fun roles(source:String):Set<String> = roles[source].orEmpty()
    fun isFunction(source:String)=source in functions
}
