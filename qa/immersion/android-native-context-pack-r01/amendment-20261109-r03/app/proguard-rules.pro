-keep class co.fallsoft.vipi.contextqa.ContextProbeInstrumentation { *; }
# Model factory class names are serialized in the verified publisher assets.
-keep class opennlp.tools.sentdetect.SentenceDetectorFactory { *; }
-keep class opennlp.tools.tokenize.TokenizerFactory { *; }
-keep class opennlp.tools.postag.POSTaggerFactory { *; }
-keep class opennlp.tools.util.featuregen.** { *; }
