import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import opennlp.tools.sentdetect.*;
import opennlp.tools.tokenize.*;
import opennlp.tools.postag.*;
import opennlp.tools.util.Span;
class SourceRoleProbe {
 static String quote(String s){return "\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";}
 static String sha(String s)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)));}
 static String hwm()throws Exception{return Files.readAllLines(Path.of("/proc/self/status")).stream().filter(x->x.startsWith("VmHWM:")).findFirst().orElse("missing");}
 public static void main(String[] a)throws Exception{
  Path models=Path.of(a[0]),data=Path.of(a[1]);long started=System.nanoTime();
  SentenceDetectorME sentence;TokenizerME tokenizer;POSTaggerME tagger;
  try(var in=Files.newInputStream(models.resolve("opennlp-en-ud-ewt-sentence-1.3-2.5.4.bin"))){sentence=new SentenceDetectorME(new SentenceModel(in));}
  try(var in=Files.newInputStream(models.resolve("opennlp-en-ud-ewt-tokens-1.3-2.5.4.bin"))){tokenizer=new TokenizerME(new TokenizerModel(in));}
  try(var in=Files.newInputStream(models.resolve("opennlp-en-ud-ewt-pos-1.3-2.5.4.bin"))){tagger=new POSTaggerME(new POSModel(in));}
  System.err.println("MODEL_LOAD_NS="+(System.nanoTime()-started));
  List<String> lines=Files.readAllLines(data.resolve("id-text.tsv"),StandardCharsets.UTF_8);long outputBytes=0;int tokenCount=0;
  for(int pass=0;pass<2;pass++){
   long begin=System.nanoTime();int count=0;int limit=pass==0?lines.size():Math.min(20,lines.size());
   for(int ci=0;ci<limit;ci++){
    String[] fields=lines.get(ci).split("\t",-1);String id=new String(Base64.getDecoder().decode(fields[0]),StandardCharsets.UTF_8),original=new String(Base64.getDecoder().decode(fields[1]),StandardCharsets.UTF_8);
    if(original.length()>180)throw new IllegalStateException("length "+id);
    Span[] sentences=sentence.sentPosDetect(original);StringBuilder out=new StringBuilder("{\"pass\":"+pass+",\"id\":"+quote(id)+",\"source_sha256\":"+quote(sha(original))+",\"tokens\":[");boolean comma=false;
    for(Span ss:sentences){String text=original.substring(ss.getStart(),ss.getEnd());Span[] ts=tokenizer.tokenizePos(text);String[] words=Span.spansToStrings(ts,text),tags=tagger.tag(words);double[] probs=tagger.probs();
     for(int ti=0;ti<ts.length;ti++){int start=ss.getStart()+ts[ti].getStart(),end=ss.getStart()+ts[ti].getEnd();if(!original.substring(start,end).equals(words[ti]))throw new IllegalStateException("substring "+id);if(comma)out.append(',');comma=true;out.append('[').append(start).append(',').append(end).append(',').append(quote(tags[ti])).append(',').append(probs[ti]).append(']');tokenCount++;}
    }out.append("]}");byte[] bytes=(out.toString()+"\n").getBytes(StandardCharsets.UTF_8);outputBytes+=bytes.length;if(outputBytes>16777216)throw new IllegalStateException("output budget");System.out.write(bytes);count++;
   }System.out.flush();System.err.println("PASS="+pass+" COUNT="+count+" WALL_NS="+(System.nanoTime()-begin)+" "+hwm());
  }System.err.println("TOKENS_CHECKED="+tokenCount+" OUTPUT_BYTES="+outputBytes+" FINAL "+hwm());
 }
}
