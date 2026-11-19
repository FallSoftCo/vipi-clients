import Foundation

/// Language identifiers exposed by the already bundled ML Kit translation API.
/// This catalog is independent of installed translation models and TTS voices.
/// Greetings are known-language UI input, never practice-language output.
enum LocalLanguageCatalog {
    static let languages: [VipiLanguage] = [
        .init(id: "en", name: "English", localName: "English", exampleGreeting: "Hello! How are you?"),
        .init(id: "es", name: "Spanish", localName: "Español", exampleGreeting: "¡Hola! ¿Cómo estás?"),
        .init(id: "fr", name: "French", localName: "Français", exampleGreeting: "Bonjour ! Comment vas-tu ?"),
        .init(id: "de", name: "German", localName: "Deutsch", exampleGreeting: "Hallo! Wie geht es dir?"),
        .init(id: "it", name: "Italian", localName: "Italiano", exampleGreeting: "Ciao! Come stai?"),
        .init(id: "pt", name: "Portuguese", localName: "Português", exampleGreeting: "Olá! Como você está?"),
        .init(id: "ja", name: "Japanese", localName: "日本語", exampleGreeting: "こんにちは！元気ですか？"),
        .init(id: "ko", name: "Korean", localName: "한국어", exampleGreeting: "안녕하세요! 잘 지내세요?"),
        .init(id: "zh", name: "Chinese", localName: "中文", exampleGreeting: "你好！你好吗？"),
        .init(id: "ar", name: "Arabic", localName: "العربية", exampleGreeting: "مرحبًا! كيف حالك؟"),
        .init(id: "sw", name: "Swahili", localName: "Kiswahili", exampleGreeting: "Habari! Unaendeleaje?"),
        .init(id: "af", name: "Afrikaans", localName: "Afrikaans", exampleGreeting: "Hallo!"),
        .init(id: "be", name: "Belarusian", localName: "Беларуская", exampleGreeting: "Прывітанне!"),
        .init(id: "bg", name: "Bulgarian", localName: "Български", exampleGreeting: "Здравей!"),
        .init(id: "bn", name: "Bengali", localName: "বাংলা", exampleGreeting: "নমস্কার!"),
        .init(id: "ca", name: "Catalan", localName: "Català", exampleGreeting: "Hola!"),
        .init(id: "cs", name: "Czech", localName: "Čeština", exampleGreeting: "Ahoj!"),
        .init(id: "cy", name: "Welsh", localName: "Cymraeg", exampleGreeting: "Helo!"),
        .init(id: "da", name: "Danish", localName: "Dansk", exampleGreeting: "Hej!"),
        .init(id: "el", name: "Greek", localName: "Ελληνικά", exampleGreeting: "Γεια σου!"),
        .init(id: "eo", name: "Esperanto", localName: "Esperanto", exampleGreeting: "Saluton!"),
        .init(id: "et", name: "Estonian", localName: "Eesti", exampleGreeting: "Tere!"),
        .init(id: "fa", name: "Persian", localName: "فارسی", exampleGreeting: "سلام!"),
        .init(id: "fi", name: "Finnish", localName: "Suomi", exampleGreeting: "Hei!"),
        .init(id: "ga", name: "Irish", localName: "Gaeilge", exampleGreeting: "Dia duit!"),
        .init(id: "gl", name: "Galician", localName: "Galego", exampleGreeting: "Ola!"),
        .init(id: "gu", name: "Gujarati", localName: "ગુજરાતી", exampleGreeting: "નમસ્તે!"),
        .init(id: "he", name: "Hebrew", localName: "עברית", exampleGreeting: "שלום!"),
        .init(id: "hi", name: "Hindi", localName: "हिन्दी", exampleGreeting: "नमस्ते!"),
        .init(id: "hr", name: "Croatian", localName: "Hrvatski", exampleGreeting: "Bok!"),
        .init(id: "ht", name: "Haitian Creole", localName: "Kreyòl ayisyen", exampleGreeting: "Bonjou!"),
        .init(id: "hu", name: "Hungarian", localName: "Magyar", exampleGreeting: "Szia!"),
        .init(id: "id", name: "Indonesian", localName: "Bahasa Indonesia", exampleGreeting: "Halo!"),
        .init(id: "is", name: "Icelandic", localName: "Íslenska", exampleGreeting: "Halló!"),
        .init(id: "ka", name: "Georgian", localName: "ქართული", exampleGreeting: "გამარჯობა!"),
        .init(id: "kn", name: "Kannada", localName: "ಕನ್ನಡ", exampleGreeting: "ನಮಸ್ಕಾರ!"),
        .init(id: "lt", name: "Lithuanian", localName: "Lietuvių", exampleGreeting: "Labas!"),
        .init(id: "lv", name: "Latvian", localName: "Latviešu", exampleGreeting: "Sveiki!"),
        .init(id: "mk", name: "Macedonian", localName: "Македонски", exampleGreeting: "Здраво!"),
        .init(id: "mr", name: "Marathi", localName: "मराठी", exampleGreeting: "नमस्कार!"),
        .init(id: "ms", name: "Malay", localName: "Bahasa Melayu", exampleGreeting: "Apa khabar?"),
        .init(id: "mt", name: "Maltese", localName: "Malti", exampleGreeting: "Bongu!"),
        .init(id: "nl", name: "Dutch", localName: "Nederlands", exampleGreeting: "Hallo!"),
        .init(id: "no", name: "Norwegian", localName: "Norsk", exampleGreeting: "Hei!"),
        .init(id: "pl", name: "Polish", localName: "Polski", exampleGreeting: "Cześć!"),
        .init(id: "ro", name: "Romanian", localName: "Română", exampleGreeting: "Bună!"),
        .init(id: "ru", name: "Russian", localName: "Русский", exampleGreeting: "Привет!"),
        .init(id: "sk", name: "Slovak", localName: "Slovenčina", exampleGreeting: "Ahoj!"),
        .init(id: "sl", name: "Slovenian", localName: "Slovenščina", exampleGreeting: "Živjo!"),
        .init(id: "sq", name: "Albanian", localName: "Shqip", exampleGreeting: "Përshëndetje!"),
        .init(id: "sv", name: "Swedish", localName: "Svenska", exampleGreeting: "Hej!"),
        .init(id: "ta", name: "Tamil", localName: "தமிழ்", exampleGreeting: "வணக்கம்!"),
        .init(id: "te", name: "Telugu", localName: "తెలుగు", exampleGreeting: "నమస్కారం!"),
        .init(id: "th", name: "Thai", localName: "ไทย", exampleGreeting: "สวัสดี!"),
        .init(id: "tl", name: "Tagalog", localName: "Tagalog", exampleGreeting: "Kumusta!"),
        .init(id: "tr", name: "Turkish", localName: "Türkçe", exampleGreeting: "Merhaba!"),
        .init(id: "uk", name: "Ukrainian", localName: "Українська", exampleGreeting: "Привіт!"),
        .init(id: "ur", name: "Urdu", localName: "اردو", exampleGreeting: "سلام!"),
        .init(id: "vi", name: "Vietnamese", localName: "Tiếng Việt", exampleGreeting: "Xin chào!"),
    ]
    static let codes = Set(languages.map(\.id))
    static func canonicalCode(_ identifier: String) -> String {
        let code = identifier.replacingOccurrences(of: "_", with: "-").split(separator: "-").first.map(String.init) ?? identifier
        switch code {
        case "nb": return "no"
        case "iw": return "he"
        case "in": return "id"
        case "fil": return "tl"
        default: return code
        }
    }
    static func appleIdentifier(_ code: String) -> String { code == "no" ? "nb" : code }
}
