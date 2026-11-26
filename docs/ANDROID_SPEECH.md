# Android offline speech

`LocalVoice` first selects an installed, non-network system voice for the language.
An unavailable voice or failed synthesis uses the pinned eSpeak fallback. The shared data contains
57 dictionaries for the 59-language translation catalog. Galician and Filipino
(Tagalog) require a suitable installed voice. The manifest maps each canonical
app code to its engine voice and dictionary. Mandarin maps to voice and dictionary
`cmn`. Norwegian Bokmål uses voice `nb` and dictionary `no`.

The Japanese eSpeak voice accepts kana only. `JapaneseSpeechReading` reuses the
already packaged Kuromoji/IPADIC tokenizer's pronunciation/reading fields for
fallback audio. It preserves punctuation and rejects unresolved Han characters.
Message text, displayed transliteration and immersion matching are unchanged.
Names and ambiguous readings still require linguistic/listening evaluation;
nonempty PCM alone does not prove correct pronunciation.

The source revisions and licenses are retained in `android/vendor`. Regenerate
the shared speech data on disk with the existing host compiler, without downloads:

```sh
python3 scripts/build-android-speech-data.py \
  --cmake "$ANDROID_HOME/cmake/3.22.1/bin/cmake" \
  --ninja "$ANDROID_HOME/cmake/3.22.1/bin/ninja" \
  --build-dir /absolute/disk/build-speech \
  --output /absolute/disk/regenerated-speech \
  --verify-against android/app/src/main/assets/speech/espeak-ng-699e7969
```

The manifest binds every generated file to its byte length and SHA-256. The
57 dictionaries and shared data total 17,582,763 bytes across 413 data files.
The 46 additional dictionaries add 13,748,722 bytes to the prior 11-language pack.
Upstream documents fully diacritized text as the supported Arabic input. Script reading, offline
translation, engine output and pronunciation each require their own checks. JNI serializes engine access,
uses literal UTF-8 input, supports per-utterance cancellation and removes failed
private audio. Pair playback normalizes to one 24 kHz mono PCM stream. Reusable
voice data is separate from private rendered message audio.
