# Keep rules are added alongside qualified native protocol/provider dependencies.
# Kuromoji resolves dictionary binaries relative to its tokenizer's Java package.
-keepnames class com.atilika.kuromoji.ipadic.**
-keeppackagenames com.atilika.kuromoji.ipadic
# Factory class names are serialized in the pinned OpenNLP model assets.
-keep class opennlp.tools.sentdetect.SentenceDetectorFactory { *; }
-keep class opennlp.tools.tokenize.TokenizerFactory { *; }
-keep class opennlp.tools.postag.POSTaggerFactory { *; }
-keep class opennlp.tools.util.featuregen.** { *; }
