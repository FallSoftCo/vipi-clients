#include <jni.h>
#include <string>
#include <vector>
#include <new>
#include "compact_lang_det.h"
#include "encodings.h"
#include "lang_script.h"

extern "C" JNIEXPORT jobjectArray JNICALL
Java_co_fallsoft_vipi_LocalLanguageDetector_detect(JNIEnv* env, jobject, jbyteArray input) {
    if (!input) return nullptr;
    const jsize size = env->GetArrayLength(input);
    if (size <= 0 || size > 65536) return nullptr;
    try {
    std::vector<char> bytes(static_cast<size_t>(size) + 1, 0);
    env->GetByteArrayRegion(input, 0, size, reinterpret_cast<jbyte*>(bytes.data()));
    if (env->ExceptionCheck()) return nullptr;
    CLD2::CLDHints hints{};
    hints.encoding_hint = CLD2::UNKNOWN_ENCODING;
    hints.language_hint = CLD2::UNKNOWN_LANGUAGE;
    CLD2::Language languages[3];
    int percentages[3], textBytes = 0, validBytes = 0;
    double scores[3];
    bool reliable = false;
    CLD2::ExtDetectLanguageSummaryCheckUTF8(bytes.data(), size, true, &hints, 0,
        languages, percentages, scores, nullptr, &textBytes, &reliable, &validBytes);
    if (validBytes < size) return nullptr;
    const auto stringClass = env->FindClass("java/lang/String");
    if (!stringClass) return nullptr;
    const auto result = env->NewObjectArray(7, stringClass, nullptr);
    env->DeleteLocalRef(stringClass);
    if (!result) return nullptr;
    const std::string values[] = {reliable ? "1" : "0",
        CLD2::LanguageCode(languages[0]), std::to_string(percentages[0]),
        CLD2::LanguageCode(languages[1]), std::to_string(percentages[1]),
        CLD2::LanguageCode(languages[2]), std::to_string(percentages[2])};
    for (int i = 0; i < 7; ++i) {
        const auto value = env->NewStringUTF(values[i].c_str());
        if (!value) return nullptr;
        env->SetObjectArrayElement(result, i, value);
        env->DeleteLocalRef(value);
        if (env->ExceptionCheck()) return nullptr;
    }
    return result;
    } catch (const std::bad_alloc&) {
        // Never allow a native allocation failure to unwind across JNI.
        return nullptr;
    }
}
