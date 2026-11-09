package co.fallsoft.vipi
import org.json.JSONObject
internal class FrozenSourceCase(bytes:ByteArray,expectedSHA:String) {
    private val table=JSONObject(bytes.toString(Charsets.UTF_8))
    private val lower:List<IntRange>;private val upper:List<IntRange>;private val title:List<IntRange>
    init {require(FrozenContextTokenizer.sha256(bytes)==expectedSHA && table.getString("unicode_version")=="15.0.0");lower=ranges("lower");upper=ranges("upper");title=ranges("title")}
    private fun ranges(key:String):List<IntRange>{val a=table.getJSONArray(key);var end = -1;return (0 until a.length()).map{val r=a.getJSONArray(it);require(r.length()==2);val lo=r.getInt(0);val hi=r.getInt(1);require(lo>end && hi>=lo && hi<=0x10ffff);end=hi;lo..hi}}
    private fun contains(v:Int,rs:List<IntRange>):Boolean{var lo=0;var hi=rs.size;while(lo<hi){val m=lo+(hi-lo)/2;if(rs[m].last<v)lo=m+1 else hi=m};return lo<rs.size && rs[lo].first<=v}
    fun isLower(text:String):Boolean{var found=false;for(v in text.codePoints().toArray()){if(contains(v,lower))found=true else if(contains(v,upper)||contains(v,title))return false};return found}
    fun firstIsUpper(text:String)=text.isNotEmpty() && contains(text.codePointAt(0),upper)
}
