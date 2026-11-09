package co.fallsoft.vipi

import android.content.res.AssetManager
import android.database.sqlite.SQLiteDatabase
import android.os.Looper
import android.system.Os
import java.io.Closeable
import java.io.File
import co.fallsoft.vipi.FrozenContextTokenizer.Range

/** Explicitly constructed, offline evidence owner. No application/chat call site.
 * Caller owns immutable, content-addressed dictionary/pack files for this owner's
 * lifetime. A catalog refresh needs a NEW owner; failures do not trigger retries.
 * Initialize/use/close on a background worker. Methods serialize OpenNLP and DB use.
 */
internal class SourceContextEvidenceOwner(
    private val assets:AssetManager,
    private val packFile:File,
    private val englishDictionary:File,
    private val spanishDictionary:File
):Closeable {
    enum class Phase { UNINITIALIZED, READY, FAILED, CLOSED }
    data class Failure(val stage:String,val exceptionType:String,val reason:String)
    data class Status(val phase:Phase,val failure:Failure?=null)
    sealed class Inspection {
        data class Evidence(val original:String,val catalogIdentity:String,val nativeWords:List<Range>,
            val recognition:LexicalSourceRecognition.Snapshot,val roles:EnglishRoleEvidence,
            val matches:Map<Range,FrozenContextPackReader.Assessment>):Inspection()
        data class Unavailable(val original:String,val suppliedProtection:List<Range>,val status:Status):Inspection()
    }
    private data class Stamp(val device:Long,val inode:Long,val bytes:Long,val modified:Long,val changed:Long)
    private data class Loaded(val pack:FrozenContextPackReader,val roles:EnglishSourceRoleProvider,
        val dictionary:SQLiteDatabase,val stamps:Map<File,Stamp>)
    private var loaded:Loaded?=null
    @Volatile private var current=Status(Phase.UNINITIALIZED)
    private fun worker() { check(Looper.myLooper()!=Looper.getMainLooper()) { "Source context evidence requires a background worker" } }
    private fun stamp(file:File):Stamp {
        require(file.isAbsolute && file.canonicalFile==file.absoluteFile && file.isFile)
        require(listOf("-wal","-shm","-journal").none{File(file.path+it).exists()})
        val s=Os.stat(file.path)
        return Stamp(s.st_dev,s.st_ino,s.st_size,s.st_mtime,s.st_ctime)
    }
    // UI status observation must not wait for background hashing/model loading.
    fun status():Status=current
    /** Hash/metadata validation and model reconstruction occur only here, once. */
    @Synchronized fun initialize():Status {
        worker();if(current.phase!=Phase.UNINITIALIZED)return current
        var db:SQLiteDatabase?=null;var stage="immutable_files"
        try {
            val files=listOf(packFile,englishDictionary,spanishDictionary)
            val before=files.associateWith(::stamp)
            stage="unicode_table"
            val bytes=assets.open("source-context/unicode15.json").use{input->
                val buffer=ByteArray(51279);var count=0
                while(count<buffer.size){val n=input.read(buffer,count,buffer.size-count);if(n<0)break;count+=n}
                require(count==51278);buffer.copyOf(count)
            }
            val tokenizer=FrozenContextTokenizer(bytes)
            stage="pack_dictionary_validation"
            val pack=FrozenContextPackReader(packFile,PACK_SHA,mapOf(
                "policy_sha256" to "d18fbde6b978d7f3c2dc8f57902d6312524c02ce6c1ab23f2c4227812c47afdb",
                "input_manifest_sha256" to "eee17bcdc5ed5515c548788a30c72ddb7469bcd9d7d59dc261a030071b51f23d"),
                mapOf("en" to englishDictionary,"es" to spanishDictionary),tokenizer)
            stage="source_database"
            db=SQLiteDatabase.openDatabase(englishDictionary.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
            stage="model_load"
            val roles=EnglishSourceRoleProvider(assets)
            require(files.associateWith(::stamp)==before){"Immutable input changed while initializing"}
            loaded=Loaded(pack,roles,db,before);db=null;current=Status(Phase.READY)
        } catch(e:Exception) {
            db?.close();current=Status(Phase.FAILED,Failure(stage,e.javaClass.name,"Evidence initialization failed; create a new owner only after explicit repair"))
        }
        return current
    }
    /** Does not initialize implicitly, rehash dictionaries, reconstruct models,
     * select alternate heads, create masks from learned context, or approve output.
     * Caller protection remains in every unavailable result.
     */
    @Synchronized fun inspect(original:String,sourceKeys:Map<Range,List<String>>,suppliedProtection:List<Range>):Inspection {
        worker()
        fun unavailable()=Inspection.Unavailable(original,suppliedProtection.toList(),current)
        val state=loaded?:return unavailable()
        if(current.phase!=Phase.READY)return unavailable()
        var stage="source_input"
        try {
            require(original.length<=16384 && sourceKeys.size<=16384 && suppliedProtection.size<=4096)
            require(sourceKeys.values.sumOf{it.size.toLong()}<=4096)
            stage="immutable_file_stamps"
            require(state.stamps.all{(file,old)->stamp(file)==old}){"Input identity changed"}
            // Stamp checks detect ordinary replacement, truncation or sidecars;
            // they do not authenticate hostile same-stat mutation. Immutability
            // is an explicit owner contract, not an mtime-based trust decision.
            stage="source_recognition"
            val recognition=LexicalConcordance.sourceRecognition(state.dictionary,original,"en",suppliedProtection)
                ?: return Inspection.Unavailable(original,suppliedProtection.toList(),
                    Status(Phase.FAILED,Failure(stage,"UnassessedSource",
                        "This source cannot be assessed within the native geometry/analysis bounds; the loaded owner remains ready")))
            val words=LocalImmersion.words(original,"en").map{Range(it.first,it.last+1)}
            stage="source_role"
            val role=state.roles.inspect(original,"en",words,suppliedProtection).snapshot
            stage="context_match"
            val matches=sourceKeys.entries.associate{(focus,keys)->focus to state.pack.assess(original,words,focus,keys.toList())}
            return Inspection.Evidence(original,"source-context-v1:$PACK_SHA",words,recognition,role,matches)
        } catch(e:Exception) {
            if((e is IllegalArgumentException || e is org.json.JSONException) && stage in setOf("source_input","context_match")) {
                return Inspection.Unavailable(original,suppliedProtection.toList(),
                    Status(Phase.FAILED,Failure(stage,e.javaClass.name,"This source request was rejected; the loaded owner remains ready")))
            }
            current=Status(Phase.FAILED,Failure(stage,e.javaClass.name,"Evidence inspection failed; supplied protections remain authoritative"))
            loaded=null;state.dictionary.close();return unavailable()
        }
    }
    /** Serialized access to the already authenticated dependencies; no rehash/model reload.
     * Callback must remain synchronous and must not retain the SQLite handle. */
    @Synchronized internal fun <T> withCandidateDependencies(expectedEnglishSHA256:String,
        body:(FrozenContextPackReader,SQLiteDatabase)->T):T {
        worker();check(current.phase==Phase.READY)
        val state=checkNotNull(loaded)
        require(state.pack.metadata.getValue("dictionary_en_sha256")==expectedEnglishSHA256)
        require(state.stamps.all{(file,old)->stamp(file)==old}) { "Immutable dependency changed" }
        return body(state.pack,state.dictionary)
    }
    @Synchronized override fun close() {
        worker();loaded?.dictionary?.close();loaded=null
        current=Status(Phase.CLOSED,current.failure)
    }
    companion object { const val PACK_SHA="cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4" }
}
