import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import opennlp.tools.sentdetect.*;
import opennlp.tools.tokenize.*;
import opennlp.tools.postag.*;
import opennlp.tools.util.Span;
class SourceProbe {
 static String quote(String s) { StringBuilder b=new StringBuilder("\""); for(char c:s.toCharArray()){switch(c){case '"':b.append("\\\"");break;case '\\':b.append("\\\\");break;case '\n':b.append("\\n");break;case '\r':b.append("\\r");break;case '\t':b.append("\\t");break;default:if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}}return b.append('"').toString(); }
 static String hwm() throws Exception {return Files.readAllLines(Path.of("/proc/self/status")).stream().filter(x->x.startsWith("VmHWM:")).findFirst().orElse("missing");}
 public static void main(String[] a) throws Exception {
  long loadStart=System.nanoTime();Path root=Path.of(a[0]);
  SentenceDetectorME sentence;TokenizerME tokenizer;POSTaggerME tagger;
  try(var in=Files.newInputStream(root.resolve("opennlp-en-ud-ewt-sentence-1.3-2.5.4.bin"))){sentence=new SentenceDetectorME(new SentenceModel(in));}
  try(var in=Files.newInputStream(root.resolve("opennlp-en-ud-ewt-tokens-1.3-2.5.4.bin"))){tokenizer=new TokenizerME(new TokenizerModel(in));}
  try(var in=Files.newInputStream(root.resolve("opennlp-en-ud-ewt-pos-1.3-2.5.4.bin"))){tagger=new POSTaggerME(new POSModel(in));}
  System.err.println("MODEL_LOAD_NS="+(System.nanoTime()-loadStart));
  List<String> lines=Files.readAllLines(root.resolve("id-text.tsv"),StandardCharsets.UTF_8);
  for(int pass=0;pass<3;pass++) {
   long begin=System.nanoTime();int count=0;
   for(String line:lines){String[] fields=line.split("\t",-1);String id=new String(Base64.getDecoder().decode(fields[0]),StandardCharsets.UTF_8);String original=new String(Base64.getDecoder().decode(fields[1]),StandardCharsets.UTF_8);
    Span[] sentences=sentence.sentPosDetect(original); double[] sp=sentence.getSentenceProbabilities();
    StringBuilder out=new StringBuilder("{\"pass\":"+pass+",\"id\":"+quote(id)+",\"sentences\":[");
    for(int si=0;si<sentences.length;si++){if(si>0)out.append(',');Span ss=sentences[si];String text=original.substring(ss.getStart(),ss.getEnd());Span[] ts=tokenizer.tokenizePos(text);double[] tp=tokenizer.getTokenProbabilities();String[] words=Span.spansToStrings(ts,text);String[] tags=tagger.tag(words);double[] probs=tagger.probs();
     out.append("{\"start\":").append(ss.getStart()).append(",\"end\":").append(ss.getEnd()).append(",\"text\":").append(quote(text)).append(",\"score\":").append(sp[si]).append(",\"tokens\":[");
     for(int ti=0;ti<ts.length;ti++){if(ti>0)out.append(',');int start=ss.getStart()+ts[ti].getStart(),end=ss.getStart()+ts[ti].getEnd();boolean exact=original.substring(start,end).equals(words[ti]);if(!exact)throw new IllegalStateException("Substring mismatch "+id);
      out.append("{\"start\":").append(start).append(",\"end\":").append(end).append(",\"text\":").append(quote(words[ti])).append(",\"pos\":").append(quote(tags[ti])).append(",\"pos_score\":").append(probs[ti]).append(",\"token_score\":").append(tp[ti]).append(",\"substring_exact\":true}");
     }out.append("]}");
    }out.append("]}");System.out.println(out);count++;
   }
   System.err.println("PASS="+pass+" COUNT="+count+" WALL_NS="+(System.nanoTime()-begin)+" "+hwm());
  }
  System.err.println("FINAL "+hwm());
 }
}
