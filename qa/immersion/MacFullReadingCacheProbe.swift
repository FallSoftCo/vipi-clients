import Foundation
import Darwin

/// Executes the actual production actor/cache source without building a package
/// or app. Mirrors its four pending XCTest cases; no UI/provider acceptance.
private actor Probe {
    private var calls: [String: Int] = [:]
    private var held: [CheckedContinuation<Void, Never>] = []
    func read(_ text: String, _ language: String) async -> FullReading? {
        calls[text + language, default: 0] += 1
        if text == "held" { await withCheckedContinuation { held.append($0) } }
        return text == "unknown" ? nil : .init(text: text + language, provenance: .authored)
    }
    func count(_ text: String, _ language: String) -> Int { calls[text + language, default: 0] }
    func waiting() -> Int { held.count }
    func release() { let all = held; held.removeAll(); for value in all { value.resume() } }
}
@main struct CacheProbe {
    enum Failure: Error { case producerDidNotReachGate }
    @MainActor private static func wait(_ probe: Probe, count: Int) async throws {
        for _ in 0..<200 {
            if await probe.waiting() == count { return }
            try await Task.sleep(for: .milliseconds(5))
        }
        throw Failure.producerDidNotReachGate
    }
    @MainActor static func main() async throws {
        precondition(CommandLine.arguments.count == 2)
        let output = URL(fileURLWithPath: CommandLine.arguments[1])
        precondition(!FileManager.default.fileExists(atPath: output.path))
        let watchdog = DispatchSource.makeTimerSource(queue: .global())
        watchdog.schedule(deadline: .now() + 30); watchdog.setEventHandler { exit(124) }; watchdog.resume()
        defer { watchdog.cancel() }
        var rows: [[String: Any]] = []
        var began = ProcessInfo.processInfo.systemUptime
        do {
            let probe = Probe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
            let first = Task { await cache.resolve(text: "held", language: "zh") }
            let second = Task { await cache.resolve(text: "held", language: "zh") }
            try await wait(probe, count: 1)
            let other = await cache.resolve(text: "other", language: "ja")
            precondition(other?.text == "otherja")
            await probe.release()
            let a = await first.value, b = await second.value, count = await probe.count("held", "zh")
            precondition(a == b && a?.text == "heldzh" && count == 1)
            for _ in 0..<3 { let missing = await cache.resolve(text: "unknown", language: "zh"); precondition(missing == nil) }
            let misses = await probe.count("unknown", "zh")
            precondition(misses == 1 && cache.count == 3)
            rows.append(["case": "coalescing_negative_cache_independent_key", "passed": true,
                         "milliseconds": (ProcessInfo.processInfo.systemUptime - began) * 1000])
        }
        began = ProcessInfo.processInfo.systemUptime
        do {
            let probe = Probe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
            let old = Task { await cache.resolve(text: "held", language: "zh") }
            try await wait(probe, count: 1); cache.removeAll()
            let new = Task { await cache.resolve(text: "held", language: "zh") }
            try await wait(probe, count: 2); await probe.release()
            let obsolete = await old.value, fresh = await new.value
            precondition(obsolete == nil && fresh?.text == "heldzh" && cache.count == 1)
            precondition(cache.cached(text: "held", language: "zh") == fresh)
            rows.append(["case": "reset_rejects_late_completion", "passed": true,
                         "milliseconds": (ProcessInfo.processInfo.systemUptime - began) * 1000])
        }
        began = ProcessInfo.processInfo.systemUptime
        do {
            let probe = Probe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
            let first = Task { await cache.resolve(text: "held", language: "zh") }
            let second = Task { await cache.resolve(text: "held", language: "zh") }
            try await wait(probe, count: 1); first.cancel(); await probe.release()
            let a = await first.value, b = await second.value
            precondition(a == nil && b?.text == "heldzh" && cache.cached(text: "held", language: "zh") == b)
            rows.append(["case": "cancelled_waiter_does_not_cancel_shared_work", "passed": true,
                         "prompt_cancellation_claimed": false,
                         "milliseconds": (ProcessInfo.processInfo.systemUptime - began) * 1000])
        }
        began = ProcessInfo.processInfo.systemUptime
        do {
            let probe = Probe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
            for text in ["é", "e\u{301}"] { _ = await cache.resolve(text: text, language: "zh") }
            _ = await cache.resolve(text: "é", language: "ja"); precondition(cache.count == 3)
            for index in 0..<129 { _ = await cache.resolve(text: "row\(index)", language: "zh") }
            precondition(cache.count == 128 && cache.cached(text: "é", language: "zh") == nil)
            precondition(cache.cached(text: "row128", language: "zh")?.text == "row128zh")
            let tooLong = await cache.resolve(text: String(repeating: "字", count: 16_385), language: "zh")
            let unsupported = await cache.resolve(text: "hello", language: "en")
            precondition(tooLong == nil && unsupported == nil && cache.count == 128)
            cache.removeAll(); precondition(cache.count == 0)
            rows.append(["case": "exact_encoding_language_bounds_eviction", "passed": true,
                         "milliseconds": (ProcessInfo.processInfo.systemUptime - began) * 1000])
        }
        var usage = rusage(); _ = getrusage(RUSAGE_SELF, &usage)
        let result: [String: Any] = ["schema": "vipi-full-reading-cache-cli-1", "cases": rows,
            "peak_rss_bytes": usage.ru_maxrss, "actual_production_cache_source": true,
            "scope": "Existing macOS VM CLI, no package, app, XCTest, provider, or UI qualification"]
        try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
    }
}
