# Android offline speech

`LocalVoice` first selects an installed, non-network system voice for the language.
An unavailable voice or failed synthesis uses the pinned eSpeak fallback. The
fallback contains English, Spanish, French, German, Italian, Portuguese, Japanese,
Korean, Mandarin Chinese, Arabic and Swahili dictionaries. It does not download
voices. An advertised Android voice is not evidence that synthesis works.

The Japanese eSpeak voice accepts kana only. `JapaneseSpeechReading` reuses the
already packaged Kuromoji/IPADIC tokenizer's pronunciation/reading fields for
fallback audio. It preserves punctuation and rejects unresolved Han characters.
Message text, displayed transliteration and immersion matching are unchanged.
Names and ambiguous readings still require linguistic/listening evaluation;
nonempty PCM alone does not prove correct pronunciation.

The source revisions and licenses are retained in `android/vendor`. Regenerate
the 11-language data on disk with the existing host compiler, without downloads:

```sh
python3 scripts/build-android-speech-data.py \
  --cmake "$ANDROID_HOME/cmake/3.22.1/bin/cmake" \
  --ninja "$ANDROID_HOME/cmake/3.22.1/bin/ninja" \
  --build-dir /absolute/disk/build-speech \
  --output /absolute/disk/regenerated-speech \
  --verify-against android/app/src/main/assets/speech/espeak-ng-699e7969
```

The manifest binds every generated file to its byte length and SHA-256. The
eleven dictionaries and shared data total 3,834,041 bytes; the nine additions
increase the previous English/Swahili data by 2,767,365 bytes. Existing shared
and English/Swahili files remain byte-identical. JNI serializes engine access,
uses literal UTF-8 input, supports per-utterance cancellation and removes failed
private audio. Pair playback normalizes to one 24 kHz mono PCM stream. Reusable
voice data is separate from private rendered message audio.
