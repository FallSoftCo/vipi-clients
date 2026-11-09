package co.fallsoft.vipi.contextqa
internal object ReviewedFrameLookup {
    private class Overflow:Exception()
    fun windows(text:String,language:String):Map<String,List<IntRange>>? {
        if(text.length>32768)return null
        val sentences=NativeGeometry.sentences(text,language)
        if(text.isNotEmpty() && sentences.isEmpty())return null
        val result=linkedMapOf<String,MutableList<IntRange>>();var count=0
        for(sentence in sentences) {
            val fragment=text.substring(sentence);val words=NativeGeometry.words(fragment,language)
            for(i in words.indices) {
                val starts=mutableListOf(words[i].first);val word=fragment.substring(words[i])
                val apostrophe=word.indexOfFirst{it=='\'' || it=='’'}
                if(language=="fr" && apostrophe>0 && apostrophe<word.lastIndex &&
                    word.substring(0,apostrophe).lowercase(java.util.Locale.ROOT) in setOf("j","l","d","t","m","n","s","c","qu"))
                    starts.add(words[i].first+apostrophe+1)
                for(j in i until minOf(words.size,i+8))for(start in starts) {
                val range=start..words[j].last
                if(range.last-range.first+1>256)continue
                val input=fragment.substring(range)
                if(input.any{it in ".!?。！？;；\r\n"})continue
                count++;if(count>4096)return null
                result.getOrPut(input){mutableListOf()}.add((sentence.first+range.first)..(sentence.first+range.last))
            }}
        }
        return result
    }
}
