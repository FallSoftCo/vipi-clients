package co.fallsoft.vipi
import java.io.File
import kotlinx.coroutines.*
import org.json.JSONObject
import co.fallsoft.vipi.core.TranslationIntegrity

fun main(args:Array<String>)=runBlocking {
    val reader=ChineseReadings(File(args[0]).readBytes())
    fun request(text:String,start:Int=0,end:Int=text.length,known:String="en",learning:String="zh",input:String?=null,generation:Long=1)=
        ManualTranslationRequest("immutable-message",text,start,end,known,learning,input,generation,1)
    var valid=true;var calls=0;var reads=0;var translatedInput="";var detectedInput="";var direction=""
    suspend fun run(selection:ManualTranslationRequest,output:String="音乐",ready:Boolean=true,stale:Boolean=false)=
        ManualTranslationResolver.resolve(selection,{valid},{_,_,_->null},{detectedInput=it;selection.knownLanguage},{_,_->ready},
            {text,from,to->calls++;translatedInput=text;direction="$from-$to";if(stale)valid=false;output},
            {text,language->reads++;if(language=="zh")reader.resolve(text).reading?.let{FullReading(it,FullReading.Provenance.LOCAL_TRANSLITERATION)}else null})
    val selected=request("We discussed music after dinner.",13,18)
    val first=run(selected);check(first.status==ManualTranslationStatus.READY&&first.result?.originalSlice=="music"&&translatedInput==selected.originalText)
    check(first.result?.reading?.text=="yīnyuè"&&first.result?.request==selected&&calls==1)
    check(first.result?.sourceContextText==selected.originalText&&first.result?.contextExpanded==true)
    check(first.result?.sourceContextStartUTF16==0&&first.result?.sourceContextEndUTF16==selected.originalText.length)
    check(run(request("银行"),"bank").status==ManualTranslationStatus.READY&&direction=="zh-en")
    val context=request("I would like to know what this word means.",2,7,"en","fr")
    run(context,"voudrais");check(detectedInput==context.originalText&&translatedInput==context.originalText)
    check(run(request("chat",known="en",learning="fr",input="fr"),"cat").status==ManualTranslationStatus.READY&&direction=="fr-en")
    check(ManualTranslationResolver.slice(request("A😀B",2,3))==null)
    check(ManualTranslationResolver.slice(request("e\u0301",0,1))==null)
    check(request("café").selectionIdentity!=request("cafe\u0301").selectionIdentity)
    check(request("word",generation=2).selectionIdentity!=request("word").selectionIdentity)
    val before=calls;check(run(request("word"),ready=false).status==ManualTranslationStatus.MODEL_NOT_READY&&calls==before)
    check(run(request("Read notes.md"),"阅读").status==ManualTranslationStatus.INVALID_RESULT)
    val beforeReads=reads;check(run(request("word"),stale=true).status==ManualTranslationStatus.STALE&&reads==beforeReads)
    valid=true
    val timeout=ManualTranslationResolver.resolve(request("word"),{true},{_,_,_->null},{"en"},{_,_->true},{_,_,_->throw ManualTranslationTimeout()},{_,_->null})
    check(timeout.status==ManualTranslationStatus.TIMEOUT)
    try {ManualTranslationResolver.resolve(request("word"),{true},{_,_,_->null},{"en"},{_,_->true},{_,_,_->throw CancellationException()},{_,_->null});error("cancelled request published")}
    catch(_:CancellationException){}
    val longContext="word ".repeat(6000)
    check(run(request(longContext,longContext.length-5,longContext.length-1)).result?.originalSlice=="word")
    val longURL="https://example.test/"+"x".repeat(9000)
    val longWhole="Go $longURL now "+"words ".repeat(2500)
    var chunks=0
    val chunked=ManualTranslationResolver.resolve(request(longWhole),{true},{_,_,_->null},{"en"},{_,_->true},{text,_,_->check(text.length<=8192&&!text.contains("https://"));chunks++;text},{_,_->null})
    check(chunked.status==ManualTranslationStatus.READY&&chunked.result?.targetText==longWhole&&chunks>=2)
    File(args[1]).writeText(JSONObject().put("passed",true).put("checks",15).put("translation_calls",calls).put("reading_calls",reads)
        .put("platform","Host JVM component execution, not Android render or model quality").toString(2))
}
