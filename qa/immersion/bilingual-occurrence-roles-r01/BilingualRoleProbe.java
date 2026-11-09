import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import opennlp.tools.postag.*;
class BilingualRoleProbe {
 static String decode(String s){return new String(Base64.getDecoder().decode(s),StandardCharsets.UTF_8);}
 static String quote(String s){return "\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";}
 static String sha(String s)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)));}
 public static void main(String[] args)throws Exception{
  long start=System.nanoTime();Map<String,POSTaggerME> models=new HashMap<>();
  for(int i=0;i<2;i++){try(var in=Files.newInputStream(Path.of(args[i]))){models.put(i==0?"en":"es",new POSTaggerME(new POSModel(in)));}}
  long bytes=0;int count=0;
  for(String line:Files.readAllLines(Path.of(args[2]),StandardCharsets.UTF_8)){
   String[] f=line.split("\t",-1);String id=f[0],lang=f[1],text=decode(f[2]);int n=f.length-3;String[] words=new String[n];int[] starts=new int[n],ends=new int[n];
   for(int i=0;i<n;i++){String[] t=f[i+3].split(":",3);starts[i]=Integer.parseInt(t[0]);ends[i]=Integer.parseInt(t[1]);words[i]=decode(t[2]);if(!text.substring(starts[i],ends[i]).equals(words[i]))throw new IllegalStateException("geometry");}
   POSTaggerME tagger=models.get(lang);String[] tags=tagger.tag(words);double[] scores=tagger.probs();if(tags.length!=n||scores.length!=n)throw new IllegalStateException("token count");
   StringBuilder out=new StringBuilder("{\"endpoint_key\":"+quote(id)+",\"language\":"+quote(lang)+",\"text_sha256\":"+quote(sha(text))+",\"tokens\":[");
   for(int i=0;i<n;i++){if(i>0)out.append(',');out.append('[').append(starts[i]).append(',').append(ends[i]).append(',').append(quote(tags[i])).append(',').append(scores[i]).append(']');}
   out.append("]}\n");byte[] b=out.toString().getBytes(StandardCharsets.UTF_8);bytes+=b.length;if(bytes>8*1024*1024)throw new IllegalStateException("output budget");System.out.write(b);count++;
  }
  System.out.flush();System.err.println("ENDPOINTS="+count+" BYTES="+bytes+" WALL_NS="+(System.nanoTime()-start));
  for(String s:Files.readAllLines(Path.of("/proc/self/status")))if(s.startsWith("VmHWM:")||s.startsWith("VmPeak:"))System.err.println(s);
 }
}
