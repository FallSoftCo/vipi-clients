import com.atilika.kuromoji.ipadic.Token;
import com.atilika.kuromoji.ipadic.Tokenizer;

/** JVM investigation only. Device latency and memory need separate measurement. */
public class JapaneseMorphologyProbe {
    public static void main(String[] args) {
        long start = System.nanoTime();
        Tokenizer tokenizer = new Tokenizer();
        System.out.println("initialization_ms=" + (System.nanoTime() - start) / 1e6);
        String[] samples = {
            "私の妹は銀行で働いています。 She will help me open an account tomorrow.",
            "18:30に会おう。今日は水面が穏やかだね。",
            "明日、銀行に行きます。生きています。生の魚と生ビール。"
        };
        for (String sample : samples) {
            start = System.nanoTime();
            for (Token token : tokenizer.tokenize(sample)) {
                System.out.println(token.getPosition() + "\t" + token.getSurface() + "\t" + token.getBaseForm()
                    + "\t" + token.getPartOfSpeechLevel1() + "\t" + token.getReading());
            }
            System.out.println("sample_ms=" + (System.nanoTime() - start) / 1e6);
        }
    }
}
