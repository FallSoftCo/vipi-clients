#include "VipiLanguageDetector.h"
#include "cld2/public/compact_lang_det.h"
#include "cld2/public/encodings.h"
#include <mutex>
#include <cstring>

extern "C" const char *vipi_detect_language(const char *utf8, size_t length) {
    if (!utf8 || length == 0 || length > 65536) return nullptr;
    static std::mutex mutex;
    std::lock_guard<std::mutex> lock(mutex);
    CLD2::Language languages[3]; int percentages[3]; double scores[3];
    int textBytes = 0, validPrefixBytes = 0; bool reliable = false;
    CLD2::CLDHints hints = {nullptr, nullptr, CLD2::UNKNOWN_ENCODING, CLD2::UNKNOWN_LANGUAGE};
    CLD2::Language language = CLD2::ExtDetectLanguageSummaryCheckUTF8(
        utf8, static_cast<int>(length), true, &hints, 0, languages,
        percentages, scores, nullptr, &textBytes, &reliable, &validPrefixBytes);
    if (validPrefixBytes != static_cast<int>(length) || !reliable) return nullptr;
    const char *code = CLD2::LanguageCode(language);
    if (std::strcmp(code, "zh-Hant") == 0) return "zh";
    const char *supported[] = {"en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw"};
    for (const char *candidate : supported) if (std::strcmp(code, candidate) == 0) return candidate;
    return nullptr;
}
