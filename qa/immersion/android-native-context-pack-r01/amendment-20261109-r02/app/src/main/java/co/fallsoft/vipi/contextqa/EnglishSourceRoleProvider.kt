package co.fallsoft.vipi.contextqa
import co.fallsoft.vipi.contextqa.FrozenContextTokenizer.Range
import java.io.File
import opennlp.tools.sentdetect.SentenceDetectorME
import opennlp.tools.sentdetect.SentenceModel
import opennlp.tools.tokenize.TokenizerME
import opennlp.tools.tokenize.TokenizerModel
import opennlp.tools.postag.POSTaggerME
import opennlp.tools.postag.POSModel

/** One owner thread per provider; OpenNLP adaptive state is not shared. */
internal class EnglishSourceRoleProvider(directory:File, expected:Map<String,String>) {
    data class RawToken(val range:Range,val original:String,val rawTag:String,val score:Double)
    data class Result(val snapshot:EnglishRoleEvidence,val tokens:List<RawToken>)
    private val identities=expected.toMap()
    private val sentence:SentenceDetectorME
    private val tokenizer:TokenizerME
    private val tagger:POSTaggerME
    init {
        require(expected.keys==setOf(SENTENCE,TOKEN,POS))
        for((name,sha) in expected) {
            val file=File(directory,name);require(file.length() in 1..(2L shl 20))
            require(FrozenContextTokenizer.sha256(file.readBytes())==sha)
        }
        sentence=File(directory,SENTENCE).inputStream().use{SentenceDetectorME(SentenceModel(it))}
        tokenizer=File(directory,TOKEN).inputStream().use{TokenizerME(TokenizerModel(it))}
        tagger=File(directory,POS).inputStream().use{POSTaggerME(POSModel(it))}
    }
    @Synchronized fun inspect(original:String,language:String,words:List<Range>,protection:List<Range>):Result {
        val frozenWords=words.toList();val masks=protection.toList()
        fun result(status:EnglishRoleEvidence.Status,obs:List<EnglishRoleEvidence.Observation> = emptyList(),tokens:List<RawToken> = emptyList())=
            Result(EnglishRoleEvidence(original,language,frozenWords,masks,identities,obs,status),tokens)
        if(language!="en")return result(EnglishRoleEvidence.Status.UNSUPPORTED_LANGUAGE)
        if(original.length>16384 || words.size>16384 || masks.size>4096 ||
            original.codePoints().toArray().any{it in 0xd800..0xdfff} ||
            (words+masks).any{!LexicalSourceRecognition.valid(it,original)} ||
            words.zipWithNext().any{it.first.end>it.second.start})return result(EnglishRoleEvidence.Status.INVALID_INPUT)
        if(original.isEmpty())return result(EnglishRoleEvidence.Status.EMPTY)
        val native=NativeGeometry.words(original,"en").map{Range(it.first,it.last+1)}
        if(native!=words)return result(EnglishRoleEvidence.Status.GEOMETRY_MISMATCH)
        val raw=mutableListOf<RawToken>()
        for(s in sentence.sentPosDetect(original)) {
            require(s.start>=0 && s.end>s.start && s.end<=original.length)
            val fragment=original.substring(s.start,s.end);val spans=tokenizer.tokenizePos(fragment)
            val pieces=spans.map{fragment.substring(it.start,it.end)}.toTypedArray()
            val tags=tagger.tag(pieces);val scores=tagger.probs()
            require(tags.size==pieces.size && scores.size==pieces.size)
            for(i in spans.indices) {
                val range=Range(s.start+spans[i].start,s.start+spans[i].end)
                require(range.start>=s.start && range.end<=s.end && range.end>range.start)
                require(original.substring(range.start,range.end)==pieces[i] && scores[i].isFinite())
                raw+=RawToken(range,pieces[i],tags[i],scores[i])
            }
        }
        val byRange=raw.groupBy{it.range}
        val observations=words.map { r ->
            val entries=byRange[r].orEmpty();val token=entries.singleOrNull()
            val role=when(token?.rawTag){null->EnglishRoleEvidence.Role.UNKNOWN;"NOUN"->EnglishRoleEvidence.Role.NOUN;else->EnglishRoleEvidence.Role.NON_NOUN}
            EnglishRoleEvidence.Observation(r,original.substring(r.start,r.end),token?.rawTag,token?.score,role,
                masks.any{it.start<r.end && r.start<it.end},if(token==null)"lexical_geometry_not_single_exact_word" else null)
        }
        return result(EnglishRoleEvidence.Status.READY,observations,raw.toList())
    }
    companion object {
        const val SENTENCE="opennlp-en-ud-ewt-sentence-1.3-2.5.4.bin"
        const val TOKEN="opennlp-en-ud-ewt-tokens-1.3-2.5.4.bin"
        const val POS="opennlp-en-ud-ewt-pos-1.3-2.5.4.bin"
    }
}
