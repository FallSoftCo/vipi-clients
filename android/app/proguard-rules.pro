# Keep rules are added alongside qualified native protocol/provider dependencies.
# Kuromoji resolves dictionary binaries relative to its tokenizer's Java package.
-keepnames class com.atilika.kuromoji.ipadic.**
-keeppackagenames com.atilika.kuromoji.ipadic
# libsignal JNI resolves internal store callbacks using this exact return type.
# Renaming it changes the callback descriptor and breaks release session setup.
-keepnames class org.signal.libsignal.internal.NativeHandleGuard$Owner
