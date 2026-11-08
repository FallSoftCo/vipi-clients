// Execute the exact pinned CLDR rule text through system ICU, independently of Kotlin.
#include <unicode/translit.h>
#include <unicode/normalizer2.h>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    std::ifstream file(argv[1]);
    std::stringstream buffer; buffer << file.rdbuf();
    UErrorCode status = U_ZERO_ERROR;
    UParseError parse{};
    auto rules = icu::UnicodeString::fromUTF8(buffer.str());
    std::unique_ptr<icu::Transliterator> transform(icu::Transliterator::createFromRules(
        "VipiPinnedKorean", rules, UTRANS_REVERSE, parse, status));
    if (U_FAILURE(status)) { std::cerr << u_errorName(status) << " " << parse.line << ":" << parse.offset; return 3; }
    auto nfd = icu::Normalizer2::getNFDInstance(status);
    if (U_FAILURE(status)) return 4;
    std::string line;
    while (std::getline(std::cin, line)) {
        auto source = icu::UnicodeString::fromUTF8(line);
        icu::UnicodeString decomposed;
        nfd->normalize(source, decomposed, status);
        if (U_FAILURE(status)) return 5;
        transform->transliterate(decomposed);
        std::string result; decomposed.toUTF8String(result);
        std::cout << result << '\n';
    }
}
