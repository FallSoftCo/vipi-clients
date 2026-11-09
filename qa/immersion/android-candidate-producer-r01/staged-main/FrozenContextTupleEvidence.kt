package co.fallsoft.vipi
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import co.fallsoft.vipi.FrozenContextTokenizer.Range

internal class FrozenContextTupleEvidence(db:SQLiteDatabase,rules:List<FrozenContextPackReader.Rule>,heads:Map<String,FrozenContextPackReader.Head>) {
    data class Form(val id:String,val language:String,val lexeme:Long,val surface:String,val range:Range,val number:Int,val mode:Int,val features:Set<String>,val headword:String,val pos:String,val sourceSafe:Boolean,val targetSafe:Boolean,val complete:Boolean,val reasons:Set<String>)
    data class Term(val id:String,val senseID:String,val reading:String,val eligible:Boolean,val explicit:Boolean,val reasons:Set<String>)
    data class Link(val ruleID:String,val headID:String,val sourceFormID:String,val targetFormID:String,val sourceTermID:String,val targetTermID:String)
    val forms:Map<String,Form>;val terms:Map<String,Term>;val linksByRuleHead:Map<Pair<String,String>,List<Link>>
    init {
        val fs=linkedMapOf<String,Form>();val ts=linkedMapOf<String,Term>();val links=mutableListOf<Link>()
        fun text(c:Cursor,i:Int)=FrozenCandidateCatalog.text(c,i)
        fun bool(c:Cursor,i:Int):Boolean{val n=FrozenCandidateCatalog.integer(c,i);require(n in 0..1);return n==1}
        fun strings(c:Cursor,i:Int):Set<String>{val raw=text(c,i);require(raw.toByteArray().size<=16384);val a=JSONArray(raw);require(a.length()<=256);return (0 until a.length()).map{a.getString(it).also{s->require(s.toByteArray().size<=4096)}}.toSet()}
        fun hash(s:String){require(s.matches(Regex("[0-9a-f]{64}")))}
        db.rawQuery("SELECT id,language,lexeme,surface,form_range_json,number,mode,features_json,headword,pos,source_safe,target_safe,complete,original_reasons_json,source_record_sha256 FROM forms ORDER BY id",null).use{c->while(c.moveToNext()){
            val id=text(c,0);hash(id);hash(text(c,14));require(id !in fs && fs.size<4096 && c.getType(2)==Cursor.FIELD_TYPE_INTEGER)
            val lang=text(c,1);val lex=c.getLong(2);val surface=text(c,3);val r=JSONArray(text(c,4));val n=FrozenCandidateCatalog.integer(c,5);val mode=FrozenCandidateCatalog.integer(c,6);val complete=bool(c,12);val pos=text(c,9)
            require(lang in setOf("en","es") && lex>=0 && surface.isNotEmpty() && surface.length<=1024 && r.length()==2 && r.getInt(0)==0 && r.getInt(1)==surface.length && complete && mode in 1..2 && n in 0..2 && pos=="noun")
            fs[id]=Form(id,lang,lex,surface,Range(0,surface.length),n,mode,strings(c,7),text(c,8),pos,bool(c,10),bool(c,11),complete,strings(c,13))
        }}
        db.rawQuery("SELECT id,sense_id,reading,eligible,explicit,qualifiers_json,original_reasons_json,source_record_sha256 FROM terms ORDER BY id",null).use{c->while(c.moveToNext()){
            val id=text(c,0);val sense=text(c,1);val reading=text(c,2);val qualifiers=text(c,5);hash(id);hash(sense);hash(text(c,7));require(id !in ts && ts.size<8192 && reading.length<=2048 && qualifiers.toByteArray().size<=16384);JSONObject(qualifiers)
            ts[id]=Term(id,sense,reading,bool(c,3),bool(c,4),strings(c,6))
        }}
        val ruleMap=rules.associateBy{it.id};val seen=mutableSetOf<Link>()
        db.rawQuery("SELECT rule_id,head_id,source_form,target_form,source_term,target_term FROM links ORDER BY rule_id,head_id,source_form,target_form,source_term,target_term",null).use{c->while(c.moveToNext()){
            val link=Link(text(c,0),text(c,1),text(c,2),text(c,3),text(c,4),text(c,5));require(seen.add(link) && links.size<32768)
            val rule=ruleMap.getValue(link.ruleID);val h=heads.getValue(link.headID);val sf=fs.getValue(link.sourceFormID);val tf=fs.getValue(link.targetFormID);val st=ts.getValue(link.sourceTermID);val tt=ts.getValue(link.targetTermID)
            require(link.headID in rule.headIDs && h.target==rule.target && sf.language=="en" && tf.language=="es" && sf.number==tf.number && sf.pos==tf.pos && st.senseID==tt.senseID && st.eligible && tt.eligible && st.explicit && tt.explicit && st.reasons.isEmpty() && tt.reasons.isEmpty());links+=link
        }}
        require(fs.size==326 && ts.size==651 && links.size==5328)
        forms=java.util.Collections.unmodifiableMap(fs);terms=java.util.Collections.unmodifiableMap(ts);linksByRuleHead=links.groupBy{it.ruleID to it.headID}
    }
}
