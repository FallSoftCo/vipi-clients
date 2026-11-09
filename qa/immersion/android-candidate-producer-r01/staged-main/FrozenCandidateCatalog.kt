package co.fallsoft.vipi

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONObject
import java.io.Closeable
import java.io.File
import java.security.MessageDigest

/** Indexed, externally pinned evidence reader; one owner/background thread. */
internal class FrozenCandidateCatalog(private val file:File,manifestFile:File,val manifestSHA256:String,pack:FrozenContextPackReader):Closeable {
    data class Head(val id:String,val key:String,val contextID:String,val ordinary:Boolean,val conditional:Boolean,val rank:Int,
        val recordJSON:String,val auditJSON:String,val record:JSONObject,val audit:JSONObject)
    private data class Stamp(val device:Long,val inode:Long,val bytes:Long,val modified:Long,val changed:Long)
    private fun stamp():Stamp {
        require(file.isAbsolute && file.canonicalFile==file.absoluteFile && file.isFile)
        require(listOf("-wal","-shm","-journal").none{File(file.path+it).exists()})
        val s=android.system.Os.stat(file.path);return Stamp(s.st_dev,s.st_ino,s.st_size,s.st_mtime,s.st_ctime)
    }
    private val originalStamp=stamp()
    private val db:SQLiteDatabase
    val sha256:String
    val contextPackSHA256:String
    val metadata:Map<String,String>
    val bundleIdentity:String
    init {
        require(digest(manifestFile,1L shl 20)==manifestSHA256)
        val manifest=JSONObject(manifestFile.readText(Charsets.UTF_8))
        require(manifest.getString("schema")=="vipi.source-candidate-manifest.1" && manifest.getString("permission")=="disabled_research_only")
        sha256=manifest.getString("database_sha256");val deps=manifest.getJSONObject("dependencies")
        contextPackSHA256=deps.getJSONObject("context_pack").getString("sha256")
        require(contextPackSHA256==pack.contentSHA256)
        for(lang in listOf("en","es"))require(deps.getJSONObject("dictionary_$lang").getString("sha256")==pack.metadata["dictionary_${lang}_sha256"])
        require(file.length()==manifest.getLong("database_bytes") && digest(file,256L shl 20)==sha256)
        db=SQLiteDatabase.openDatabase(file.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
        try {
            db.execSQL("PRAGMA query_only=ON");db.execSQL("PRAGMA trusted_schema=OFF");db.execSQL("PRAGMA cache_size=-8192")
            fun pragma(key:String)=db.rawQuery("PRAGMA $key",null).use{require(it.moveToFirst());it.getInt(0)}
            require(pragma("application_id")==1447645257 && pragma("user_version")==1)
            val tables=setOf("metadata","candidates","head_keys","evidence","head_evidence","known_families","source_roles","function_words")
            val counts=manifest.getJSONObject("table_counts");require(counts.keys().asSequence().toSet()==tables)
            for(table in tables){val expected=counts.getInt(table);require(expected in 0..2000000 && (table!="candidates" || expected<=65536));db.rawQuery("SELECT count(*) FROM $table",null).use{require(it.moveToFirst() && it.getInt(0)==expected)}}
            val meta=linkedMapOf<String,String>();query("SELECT key,value FROM metadata"){c->val key=text(c,0);require(key !in meta);meta[key]=text(c,1)}
            require(meta["kind"]=="vipi.source-candidate-catalog" && meta["schema"]=="1" && meta["permission"]=="disabled_research_only")
            require(meta["context_pack_sha256"]==contextPackSHA256 && meta["policy_sha256"]==manifest.getString("contract_sha256"))
            for(lang in listOf("en","es"))for(suffix in listOf("_sha256","_metadata_json")){val key="dictionary_$lang$suffix";require(meta[key]==pack.metadata[key])}
            require(digest(file,256L shl 20)==sha256 && stamp()==originalStamp)
            metadata=java.util.Collections.unmodifiableMap(meta)
            bundleIdentity=hash(listOf("vipi.candidate-bundle.1",manifestSHA256,sha256,contextPackSHA256,
                meta.getValue("dictionary_en_sha256"),meta.getValue("dictionary_es_sha256"),manifest.getString("contract_sha256")).joinToString("\n"))
        } catch(e:Throwable){db.close();throw e}
    }
    @Synchronized fun heads(sourceKey:String,ordinary:Boolean):List<Head> {
        require(sourceKey.toByteArray().size<=4096);val result=mutableListOf<Head>()
        query("SELECT id,source_key,context_id,baseline,conditional,train_rank,record_json,audit_json,record_sha256,audit_sha256 FROM candidates WHERE source_key=? AND baseline=? ORDER BY id",arrayOf(sourceKey,if(ordinary)"1" else "0")){c->
            val raw=text(c,6);val audit=text(c,7);val id=text(c,0);val key=text(c,1);val cid=text(c,2)
            require(hash(raw)==text(c,8) && hash(audit)==text(c,9));val record=JSONObject(raw);val proof=JSONObject(audit)
            require(record.getString("id")==id && record.getString("source_key")==key && record.getString("context_id")==cid)
            val baseline=integer(c,3);val conditional=integer(c,4);val rank=integer(c,5)
            require(baseline in 0..1 && conditional==1-baseline && rank>=0)
            result+=Head(id,key,cid,baseline==1,conditional==1,rank,raw,audit,record,proof);require(result.size<=65536)
        };return result
    }
    @Synchronized fun keys(headID:String):List<String> {
        val result=mutableListOf<String>();query("SELECT source_key FROM head_keys WHERE head_id=? ORDER BY source_key",arrayOf(headID)){result+=text(it,0)};require(result.size<=256);return result
    }
    @Synchronized fun evidence(headID:String):List<Map<String,String>> {
        val result=mutableListOf<Map<String,String>>()
        query("SELECT h.kind,h.identity,h.evidence_id,e.value_json FROM head_evidence h JOIN evidence e ON e.id=h.evidence_id WHERE h.head_id=? ORDER BY h.kind,h.identity,h.evidence_id",arrayOf(headID)){c->result+=mapOf("kind" to text(c,0),"identity" to text(c,1),"evidence_id" to text(c,2),"value_json" to text(c,3))};return result
    }
    private fun query(sql:String,values:Array<String>?=null,body:(Cursor)->Unit){require(stamp()==originalStamp){"Immutable catalog changed"};db.rawQuery(sql,values).use{c->var n=0;while(c.moveToNext()){require(++n<=2000000);body(c)}}}
    @Synchronized override fun close(){db.close()}
    companion object {
        fun hash(text:String)=FrozenContextTokenizer.sha256(text.toByteArray(Charsets.UTF_8))
        fun digest(file:File,maximum:Long):String {
            fun sidecars(){require(listOf("-wal","-shm","-journal").none{File(file.path+it).exists()})}
            sidecars();require(file.isFile && file.length()<=maximum);val h=MessageDigest.getInstance("SHA-256");var count=0L
            file.inputStream().use{input->val buffer=ByteArray(1 shl 20);while(true){val n=input.read(buffer);if(n<0)break;count+=n;require(count<=maximum);h.update(buffer,0,n)}}
            sidecars();return h.digest().joinToString(""){"%02x".format(it.toInt() and 255)}
        }
        fun text(c:Cursor,i:Int):String {require(c.getType(i)==Cursor.FIELD_TYPE_STRING);return c.getString(i).also{require(it.toByteArray().size<=262144)}}
        fun integer(c:Cursor,i:Int):Int{require(c.getType(i)==Cursor.FIELD_TYPE_INTEGER);val n=c.getLong(i);require(n in Int.MIN_VALUE.toLong()..Int.MAX_VALUE.toLong());return n.toInt()}
    }
}
