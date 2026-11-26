#include <jni.h>
#include <espeak-ng/espeak_ng.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>

namespace {
bool initialized = false; // Calls are serialized by SwahiliSpeech's coroutine mutex.
struct Output {
    JNIEnv *env; jobject job; jmethodID cancelled; jmethodID progress;
    FILE *file; uint32_t frames = 0; bool failed = false;
    std::vector<jint> words;
};
void fail(JNIEnv *env) {
    if (!env->ExceptionCheck()) env->ThrowNew(env->FindClass("java/io/IOException"), "Local speech could not be rendered");
}
int accept(short *samples, int count, espeak_EVENT *events) {
    if (!events || !events[0].user_data) return 0;
    auto *out = static_cast<Output *>(events[0].user_data);
    if (out->env->CallBooleanMethod(out->job, out->cancelled) || out->env->ExceptionCheck()) return 1;
    for (const auto *event = events; event->type != espeakEVENT_LIST_TERMINATED; ++event) {
        if (event->type == espeakEVENT_WORD && event->text_position > 0 && event->length > 0) {
            out->words.insert(out->words.end(), {event->text_position - 1, event->length, event->sample});
        }
    }
    if (!samples || count <= 0) return 0;
    out->env->CallVoidMethod(out->job, out->progress, count);
    if (out->env->CallBooleanMethod(out->job, out->cancelled) || out->env->ExceptionCheck()) return 1;
    if (out->frames + static_cast<uint32_t>(count) > 22050u * 600u ||
        std::fwrite(samples, sizeof(short), count, out->file) != static_cast<size_t>(count)) {
        out->failed = true; return 1;
    }
    out->frames += count; return 0;
}
void le16(unsigned char *at, uint16_t value) { at[0] = value; at[1] = value >> 8; }
void le32(unsigned char *at, uint32_t value) { for (int i = 0; i < 4; ++i) at[i] = value >> (8 * i); }
}

extern "C" JNIEXPORT jint JNICALL Java_co_fallsoft_vipi_SwahiliSpeech_prepareNative(JNIEnv *env, jclass, jstring root) {
    if (!initialized) {
        const char *path = env->GetStringUTFChars(root, nullptr);
        if (!path) return 0;
        espeak_ng_InitializePath(path);
        env->ReleaseStringUTFChars(root, path);
        if (espeak_ng_Initialize(nullptr) != ENS_OK || espeak_ng_InitializeOutput(ENOUTPUT_MODE_SYNCHRONOUS, 0, nullptr) != ENS_OK) {
            fail(env); return 0;
        }
        espeak_SetSynthCallback(accept); initialized = true;
    }
    if (espeak_ng_SetVoiceByName("sw") != ENS_OK) { fail(env); return 0; }
    return espeak_ng_GetSampleRate();
}

extern "C" JNIEXPORT jintArray JNICALL Java_co_fallsoft_vipi_SwahiliSpeech_renderNative(
    JNIEnv *env, jclass, jbyteArray text, jstring destination, jobject job, jstring language) {
    const char *voice = env->GetStringUTFChars(language, nullptr);
    if (!voice) return nullptr;
    // Kotlin resolves the identifier from the packaged, versioned voice manifest.
    const bool selected = initialized && std::strlen(voice) >= 2 && std::strlen(voice) <= 3 &&
        std::strspn(voice, "abcdefghijklmnopqrstuvwxyz") == std::strlen(voice) && espeak_ng_SetVoiceByName(voice) == ENS_OK;
    env->ReleaseStringUTFChars(language, voice);
    if (!selected) { fail(env); return nullptr; }
    const jsize size = env->GetArrayLength(text);
    if (size < 1 || size > 65536) { fail(env); return nullptr; }
    std::vector<char> bytes(static_cast<size_t>(size) + 1, 0);
    env->GetByteArrayRegion(text, 0, size, reinterpret_cast<jbyte *>(bytes.data()));
    if (env->ExceptionCheck() || std::memchr(bytes.data(), 0, size)) { fail(env); return nullptr; }
    const char *path = env->GetStringUTFChars(destination, nullptr);
    if (!path) return nullptr;
    FILE *file = std::fopen(path, "wb"); env->ReleaseStringUTFChars(destination, path);
    if (!file) { fail(env); return nullptr; }
    unsigned char header[44] = {0};
    Output out{env, job, env->GetMethodID(env->GetObjectClass(job), "isCancelled", "()Z"),
        env->GetMethodID(env->GetObjectClass(job), "onFrames", "(I)V"), file};
    if (!out.cancelled || !out.progress || std::fwrite(header, 1, sizeof(header), file) != sizeof(header)) {
        std::fclose(file); fail(env); return nullptr;
    }
    espeak_ng_SetParameter(espeakRATE, 155, 0);
    // Literal UTF-8 only: neither SSML nor embedded phoneme commands are enabled.
    const auto status = espeak_ng_Synthesize(bytes.data(), bytes.size(), 0, POS_CHARACTER, 0, espeakCHARS_UTF8, nullptr, &out);
    espeak_ng_Synchronize();
    const bool cancelled = env->CallBooleanMethod(job, out.cancelled);
    const int rate = espeak_ng_GetSampleRate();
    bool ok = status == ENS_OK && !cancelled && !out.failed && out.frames > 0 && rate > 0 && !env->ExceptionCheck();
    if (ok) {
        std::memcpy(header, "RIFF", 4); le32(header + 4, 36 + out.frames * 2);
        std::memcpy(header + 8, "WAVEfmt ", 8); le32(header + 16, 16); le16(header + 20, 1); le16(header + 22, 1);
        le32(header + 24, rate); le32(header + 28, rate * 2); le16(header + 32, 2); le16(header + 34, 16);
        std::memcpy(header + 36, "data", 4); le32(header + 40, out.frames * 2);
        ok = std::fseek(file, 0, SEEK_SET) == 0 && std::fwrite(header, 1, sizeof(header), file) == sizeof(header);
    }
    if (std::fclose(file) != 0) ok = false;
    if (!ok) { fail(env); return nullptr; }
    std::vector<jint> values{rate, static_cast<jint>(out.frames)};
    values.insert(values.end(), out.words.begin(), out.words.end());
    jintArray result = env->NewIntArray(values.size());
    if (result) env->SetIntArrayRegion(result, 0, values.size(), values.data());
    return result;
}
