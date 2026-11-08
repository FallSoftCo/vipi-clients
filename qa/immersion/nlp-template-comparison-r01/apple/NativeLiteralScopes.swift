import Foundation

/// QA counterpart of the frozen Python literal policy. This does not change
/// TranslationIntegrity or claim a general Markdown/quote parser.
enum NativeLiteralScopes {
    static func collect(_ text: String, protection: [String: Any]) throws -> [NativePatternMatcher.LiteralScope] {
        let ns = text as NSString
        let full = NSRange(location: 0, length: ns.length)
        var scopes: [NativePatternMatcher.LiteralScope] = []
        // Python's Unicode \w is alphanumeric plus underscore; ICU's default
        // also includes combining marks. Spell the frozen Python class here.
        let word = #"[\p{L}\p{N}_]"#
        let boundary = "(?:(?<!\(word))(?=\(word))|(?<=\(word))(?!\(word)))"
        for key in ["existing_regex", "extra_handles_regex", "extra_number_regex"] {
            guard let frozen = protection[key] as? String else { throw ProbeError.invalid("Missing literal policy " + key) }
            let expression = frozen.replacingOccurrences(of: #"\b"#, with: boundary)
                .replacingOccurrences(of: #"[\w@]"#, with: #"[\p{L}\p{N}_@]"#)
                .replacingOccurrences(of: #"[\w]"#, with: word)
                .replacingOccurrences(of: #"\w"#, with: word)
            let regex = try NSRegularExpression(pattern: expression)
            for match in regex.matches(in: text, range: full) {
                let value = ns.substring(with: match.range)
                let kind: String
                if key == "extra_handles_regex" { kind = "handle" }
                else if key == "extra_number_regex" { kind = "number" }
                else if value.hasPrefix("http://") || value.hasPrefix("https://") { kind = "url" }
                else if value.hasPrefix("`") { kind = "code" }
                else { kind = "email" }
                scopes.append(.init(kind: kind, range: match.range))
            }
        }
        // Exact quoted_ranges control: opener precedence, one preceding slash
        // check, first unescaped closer, unmatched opener protects to EOF.
        // Single apostrophes intentionally remain outside this scanner.
        var cursor = 0
        while cursor < ns.length {
            let marker = ["```", "`", "“", "\""].first { candidate in
                cursor + candidate.utf16.count <= ns.length &&
                    ns.substring(with: .init(location: cursor, length: candidate.utf16.count)) == candidate
            }
            guard let marker, cursor == 0 || ns.substring(with: .init(location: cursor - 1, length: 1)) != "\\" else {
                cursor += 1; continue
            }
            let closing = marker == "“" ? "”" : marker
            var search = cursor + marker.utf16.count, end = ns.length
            while search < ns.length {
                let found = ns.range(of: closing, range: .init(location: search, length: ns.length - search))
                if found.location == NSNotFound { break }
                if found.location > 0 && ns.substring(with: .init(location: found.location - 1, length: 1)) == "\\" {
                    search = NSMaxRange(found); continue
                }
                end = NSMaxRange(found); break
            }
            scopes.append(.init(kind: marker.hasPrefix("`") ? "code" : "quote",
                                range: .init(location: cursor, length: end - cursor)))
            cursor = end
        }
        var seen = Set<String>()
        return scopes.sorted { a, b in
            if a.range.location != b.range.location { return a.range.location < b.range.location }
            if a.range.length != b.range.length { return a.range.length > b.range.length }
            return a.kind < b.kind
        }.filter { seen.insert("\($0.kind):\($0.range.location):\($0.range.length)").inserted }
    }
}
