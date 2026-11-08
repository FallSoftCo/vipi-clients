package co.fallsoft.vipi.opennlpqa;
import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Debug;
import android.os.Process;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import opennlp.tools.sentdetect.*;
import opennlp.tools.tokenize.*;
import opennlp.tools.postag.*;
import opennlp.tools.util.Span;
public final class ProbeInstrumentation extends Instrumentation {
 @Override public void onCreate(Bundle args){super.onCreate(args);start();}
 private String read(InputStream in)throws Exception{try(InputStream stream=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buf=new byte[8192];int n;while((n=stream.read(buf))!=-1)out.write(buf,0,n);return out.toString("UTF-8");}}
 private JSONObject memory()throws Exception{Debug.MemoryInfo m=new Debug.MemoryInfo();Debug.getMemoryInfo(m);Runtime r=Runtime.getRuntime();JSONObject j=new JSONObject();j.put("pid",Process.myPid());j.put("pss_kib",m.getTotalPss());j.put("java_heap_used_bytes",r.totalMemory()-r.freeMemory());j.put("java_heap_committed_bytes",r.totalMemory());j.put("java_heap_max_bytes",r.maxMemory());j.put("native_heap_allocated_bytes",Debug.getNativeHeapAllocatedSize());String status=read(new FileInputStream("/proc/self/status"));for(String line:status.split("\n"))if(line.startsWith("VmHWM:")||line.startsWith("VmRSS:"))j.put(line.split(":")[0],line.substring(line.indexOf(':')+1).trim());return j;}
 private void save(String name,String text)throws Exception{try(FileOutputStream out=getTargetContext().openFileOutput(name,0)){out.write(text.getBytes(StandardCharsets.UTF_8));}}
 @Override public void onStart(){Bundle result=new Bundle();JSONObject report=new JSONObject();try{
  report.put("started_nanos",System.nanoTime());report.put("memory_before",memory());long begin=System.nanoTime();
  SentenceDetectorME sentence;TokenizerME tokenizer;POSTaggerME tagger;
  try(InputStream in=getTargetContext().getAssets().open("opennlp-en-ud-ewt-sentence-1.3-2.5.4.bin")){sentence=new SentenceDetectorME(new SentenceModel(in));}
  try(InputStream in=getTargetContext().getAssets().open("opennlp-en-ud-ewt-tokens-1.3-2.5.4.bin")){tokenizer=new TokenizerME(new TokenizerModel(in));}
  try(InputStream in=getTargetContext().getAssets().open("opennlp-en-ud-ewt-pos-1.3-2.5.4.bin")){tagger=new POSTaggerME(new POSModel(in));}
  report.put("model_load_ns",System.nanoTime()-begin);report.put("memory_after_load",memory());
  JSONArray inputs=new JSONObject(read(getTargetContext().getAssets().open("inputs.json"))).getJSONArray("cases");report.put("input_count",inputs.length());JSONArray times=new JSONArray();
  try(FileOutputStream stream=getTargetContext().openFileOutput("annotations.jsonl",0)){for(int pass=0;pass<3;pass++){long start=System.nanoTime();int tokens=0;for(int ci=0;ci<inputs.length();ci++){
   JSONObject c=inputs.getJSONObject(ci);String original=c.getString("text");JSONObject out=new JSONObject().put("pass",pass).put("id",c.getString("id"));JSONArray sr=new JSONArray();Span[] ss=sentence.sentPosDetect(original);double[] sp=sentence.getSentenceProbabilities();
   for(int si=0;si<ss.length;si++){Span s=ss[si];String text=original.substring(s.getStart(),s.getEnd());Span[] spans=tokenizer.tokenizePos(text);double[] tp=tokenizer.getTokenProbabilities();String[] words=Span.spansToStrings(spans,text),tags=tagger.tag(words);double[] probs=tagger.probs();JSONArray tr=new JSONArray();
    for(int ti=0;ti<spans.length;ti++){int a=s.getStart()+spans[ti].getStart(),b=s.getStart()+spans[ti].getEnd();if(!original.substring(a,b).equals(words[ti]))throw new IllegalStateException("substring "+c.getString("id"));tr.put(new JSONObject().put("start",a).put("end",b).put("text",words[ti]).put("pos",tags[ti]).put("pos_score",probs[ti]).put("token_score",tp[ti]).put("substring_exact",true));tokens++;}
    sr.put(new JSONObject().put("start",s.getStart()).put("end",s.getEnd()).put("text",text).put("score",sp[si]).put("tokens",tr));
   }out.put("sentences",sr);stream.write((out.toString()+"\n").getBytes(StandardCharsets.UTF_8));Bundle rowStatus=new Bundle();rowStatus.putString("stream","OPENNLP_ROW:"+out.toString()+"\n");sendStatus(1,rowStatus);
  }times.put(new JSONObject().put("pass",pass).put("wall_ns",System.nanoTime()-start).put("tokens_checked",tokens).put("memory_after",memory()));}}
  report.put("passes",times);report.put("success",true);report.put("memory_final",memory());save("receipt.json",report.toString(2));result.putString("stream","OPENNLP_RECEIPT:"+report.toString()+"\n");finish(-1,result);
 }catch(Throwable e){try{StringWriter trace=new StringWriter();e.printStackTrace(new PrintWriter(trace));report.put("success",false);report.put("error",trace.toString());save("receipt.json",report.toString(2));}catch(Exception ignored){}result.putString("stream","OPENNLP_RECEIPT:"+report.toString()+"\n");finish(0,result);}}
}
