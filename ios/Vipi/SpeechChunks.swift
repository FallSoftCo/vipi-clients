import Foundation

enum SpeechChunks {
    static func plan(_ spans: [(text: String, language: String)]) -> [[(text: String, language: String)]] {
        var pieces: [(text: String, language: String)] = []
        for span in spans {
            var text = span.text[...]
            while text.count > 160 {
                let maximum = text.index(text.startIndex, offsetBy: 160)
                let prefix = text[..<maximum]
                var end = maximum
                if let boundary = prefix.lastIndex(where: { $0.isWhitespace || ".!?。！？،,;；".contains($0) }),
                   text.distance(from: text.startIndex, to: boundary) >= 60 { end = text.index(after: boundary) }
                pieces.append((String(text[..<end]), span.language)); text = text[end...]
            }
            if !text.isEmpty { pieces.append((String(text), span.language)) }
        }
        var chunks: [[(text: String, language: String)]] = []
        var current: [(text: String, language: String)] = []
        var count = 0
        for piece in pieces {
            let punctuationOnly = piece.text.allSatisfy { $0.isWhitespace || ".,!?;:。！？、؛،".contains($0) }
            if count > 0 && count + piece.text.count > 160 && !punctuationOnly { chunks.append(current); current = []; count = 0 }
            current.append(piece); count += piece.text.count
        }
        if !current.isEmpty { chunks.append(current) }
        return chunks.filter { chunk in chunk.contains { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } }
    }
}
