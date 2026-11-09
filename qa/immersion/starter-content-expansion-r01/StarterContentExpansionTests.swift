import XCTest
import Foundation
import VipiCore
@testable import Vipi

/// Private candidate qualification through the unchanged production loaders.
@MainActor final class StarterContentExpansionTests: XCTestCase {
    private struct Owner {
        let entries: [String: [String: Any]]
        let provider: SourceUnitLookup
        let trace: () -> [[String: Any]]
        let packSHA: String
    }
    private struct Hit {
        let id: String, range: NSRange, cost: Int, category: String, rank: Int, width: Int
    }
    private func encoded(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    private func ranges(_ values: [NSRange]) -> [[Int]] { values.map { [$0.location, NSMaxRange($0)] } }
    private func spans(_ value: ImmersionPresentation?) -> [[String: Any]] {
        (value?.spans ?? []).map { ["source": $0.original, "target": $0.translated,
            "reading": $0.romanization as Any? ?? NSNull(), "source_utf16": [$0.range.location, NSMaxRange($0.range)]] }
    }
    private func references(_ value: ImmersionPresentation?) -> [[String: Any]] {
        guard case .partial(let partial) = value else { return [] }
        return partial.references.map { ["scope": [$0.range.location, NSMaxRange($0.range)],
            "output_id": $0.outputID as Any? ?? NSNull(), "reference_id": $0.referenceID,
            "pack_sha": $0.catalogSHA256, "native_cost": $0.nativeSourceTokens] }
    }
    private func mixed(_ value: ImmersionPresentation?, original: String) -> String {
        var result = original
        for span in (value?.spans ?? []).reversed() {
            result = (result as NSString).replacingCharacters(in: span.range, with: span.romanization ?? span.translated)
        }
        return result
    }
    private func budget(_ count: Int, _ density: Double) -> Int {
        density > 0 ? max(1, Int(Double(count) * density)) : 0
    }
    private func hits(_ owner: Owner, trace: [[String: Any]], words: [NSRange]) throws -> [Hit] {
        try trace.filter { $0["reason"] is NSNull }.map { row in
            let id = try XCTUnwrap(row["entry_id"] as? String), entry = try XCTUnwrap(owner.entries[id])
            let endpoints = try XCTUnwrap(row["source_utf16"] as? [Int])
            let range = NSRange(location: endpoints[0], length: endpoints[1] - endpoints[0])
            let touched = words.filter { NSIntersectionRange($0, range).length > 0 }
            XCTAssertEqual(touched.first?.location, range.location)
            XCTAssertEqual(touched.last.map(NSMaxRange), NSMaxRange(range))
            return Hit(id: id + "@\(endpoints[0]):\(endpoints[1])", range: range, cost: touched.count,
                category: try XCTUnwrap(entry["category"] as? String), rank: try XCTUnwrap(entry["train_rank"] as? Int),
                width: try XCTUnwrap(entry["source_tokens"] as? [String]).count)
        }.sorted {
            if ($0.category == "content") != ($1.category == "content") { return $0.category == "content" }
            if $0.rank != $1.rank { return $0.rank < $1.rank }
            if $0.width != $1.width { return $0.width > $1.width }
            return $0.range.location < $1.range.location
        }
    }
    private func shape(_ hits: [Hit], budget: Int) -> Set<String> {
        var selected: [Hit] = [], used = 0
        for hit in hits {
            if selected.count == 128 { break }
            if used + hit.cost > budget || selected.contains(where: { NSIntersectionRange($0.range, hit.range).length > 0 }) { continue }
            selected.append(hit); used += hit.cost
        }
        return Set(selected.map(\.id))
    }
    func testTechnicalLiteralsThroughDefaultConversation() async throws {
        for target in ["ja", "sw"] {
            let engine = ConversationImmersion(modelStatus: { _ in .unsupported })
            await engine.configure(pair: .init(source: "en", target: target), density: 0.75)
            defer { engine.close() }
            for token in ["music_notes.txt", "music_notes", "_music_notes", "music__notes", "music.txt_notes", ".music_notes", "music_notes_", "music..notes_", "music.txt", "music-notes.json", "music.tar.gz", "music.JPG", "music.vipihistory", "music_notes.custom"] {
                let source = "Send \(token) and enjoy music."
                let protected = (source as NSString).range(of: token)
                let ordinary = (source as NSString).range(of: "music", options: .backwards)
                engine.selectInputLanguage("en", for: token)
                let value = await engine.result(for: source, inputLanguage: "en", messageID: token)
                let result = try XCTUnwrap(value)
                XCTAssertTrue(result.spans.contains { $0.range == ordinary }, "Ordinary music remains available: \(target)/\(token)")
                XCTAssertFalse(result.spans.contains { NSIntersectionRange($0.range, protected).length > 0 }, "Literal changed: \(target)/\(token)")
                XCTAssertEqual(engine.lastOutcome?.localTranslationCalls, 0)
            }
        }
    }
    func testFrozenComparison() async throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_CONTENT_EXPANSION_QA"] else {
            throw XCTSkip("Private candidate qualification is opt-in")
        }
        let root = URL(fileURLWithPath: path)
        func read(_ name: String) throws -> Data { try Data(contentsOf: root.appendingPathComponent(name)) }
        func object(_ name: String) throws -> [String: Any] {
            try XCTUnwrap(JSONSerialization.jsonObject(with: read(name)) as? [String: Any])
        }
        let manifest = try object("native-input-manifest.json")
        for (name, hash) in try XCTUnwrap(manifest["files"] as? [String: String]) {
            XCTAssertEqual(JapaneseStarterLookup.digest(try read(name)), hash)
        }
        let input = try object("comparison-inputs.json"), baseline = try object("baseline-expected.json")
        let pairs = try XCTUnwrap(input["pairs"] as? [String: [[String: Any]]])
        let states = try XCTUnwrap(input["states"] as? [String: [[String: Any]]])
        let packs = try XCTUnwrap(manifest["packs"] as? [String: [String: [String: String]]])
        let potential = Set(try XCTUnwrap(manifest["boundary_candidates"] as? [String]))
        let domain = try XCTUnwrap(manifest["apple_density_values"] as? [Double])
        XCTAssertEqual(domain, (0...15).map { Double($0) / 20 })
        func owner(_ target: String, _ arm: String) throws -> Owner {
            let spec = try XCTUnwrap(packs[target]?[arm])
            let data = try read(XCTUnwrap(spec["pack"])), meta = try read(XCTUnwrap(spec["manifest"]))
            let pack = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            let rows = try XCTUnwrap(pack["entries"] as? [[String: Any]])
            let entries = Dictionary(uniqueKeysWithValues: try rows.map { (try XCTUnwrap($0["id"] as? String), $0) })
            if target == "ja" {
                let loader = try JapaneseStarterLookup(data: data, manifest: meta, packMultiple: true)
                return Owner(entries: entries, provider: loader.provider(), trace: { loader.trace }, packSHA: loader.sha)
            }
            let loader = try SwahiliStarterLookup(data: data, manifest: meta, packMultiple: true)
            return Owner(entries: entries, provider: loader.provider(), trace: { loader.trace }, packSHA: loader.sha)
        }
        var plans: [String: [Double]] = [:], plannedHits: [String: [Hit]] = [:]
        var boundaries: [[String: Any]] = [], prepassCalls = 0
        for target in ["ja", "sw"] {
            let pair = "en-" + target
            for state in try XCTUnwrap(states[pair]) {
                let sid = try XCTUnwrap(state["id"] as? String), known = Set(try XCTUnwrap(state["known_ids"] as? [String]))
                let owners = try Dictionary(uniqueKeysWithValues: ["current", "candidate"].map { ($0, try owner(target, $0)) })
                for row in try XCTUnwrap(pairs[pair]) {
                    let id = try XCTUnwrap(row["id"] as? String), text = try XCTUnwrap(row["source"] as? String)
                    let key = pair + "/" + id + "/" + sid
                    var selected: Set<Double> = [0.25, 0.75]
                    if potential.contains(pair + "/" + id) {
                        let words = LocalImmersion.words(text, language: "en")
                        for arm in ["current", "candidate"] {
                            let o = try XCTUnwrap(owners[arm])
                            _ = try await o.provider.resolve(.init(original: text, pair: .init(source: "en", target: target), density: 0.75, knownConceptIDs: known))
                            prepassCalls += 1
                            let hs = try hits(o, trace: o.trace(), words: words); plannedHits[key + "/" + arm] = hs
                            let sets = domain.map { shape(hs, budget: budget(words.count, $0)) }
                            var edges: [[Double]] = []
                            for i in 1..<domain.count where !sets[i].isSuperset(of: sets[i - 1]) {
                                selected.insert(domain[i - 1]); selected.insert(domain[i]); edges.append([domain[i - 1], domain[i]])
                            }
                            boundaries.append(["key": key, "arm": arm, "native_words": ranges(words),
                                "source_hits": hs.map { ["id": $0.id, "scope": [$0.range.location, NSMaxRange($0.range)], "cost": $0.cost, "rank": $0.rank, "category": $0.category] },
                                "nonmonotone_edges": edges])
                        }
                    }
                    plans[key] = selected.sorted()
                }
            }
        }
        XCTAssertLessThanOrEqual(prepassCalls, 36)
        let plannedEvaluations = plans.values.reduce(0) { $0 + $1.count } * 2
        XCTAssertLessThanOrEqual(plannedEvaluations, 6048)
        let frozen: [String: Any] = ["plans": plans, "boundary_proofs": boundaries, "prepass_calls": prepassCalls,
            "evaluations": plannedEvaluations, "target_outputs_used_for_selection": false]
        let frozenBytes = try encoded(frozen)
        let boundaryAttachment = XCTAttachment(data: frozenBytes, uniformTypeIdentifier: "public.json")
        boundaryAttachment.name = "content-boundary-freeze-apple.json"; boundaryAttachment.lifetime = .keepAlways; add(boundaryAttachment)
        var output = Data(), evaluations = 0, rows = 0, baselineDirect = 0, baselineRoute = 0
        let started = ProcessInfo.processInfo.systemUptime
        for target in ["ja", "sw"] {
            let pair = "en-" + target
            for state in try XCTUnwrap(states[pair]) {
                let sid = try XCTUnwrap(state["id"] as? String), knownArray = try XCTUnwrap(state["known_ids"] as? [String])
                let known = Set(knownArray)
                let owners = try Dictionary(uniqueKeysWithValues: ["current", "candidate"].map { ($0, try owner(target, $0)) })
                var engines: [String: ConversationImmersion] = [:]
                defer { for engine in engines.values { engine.close() } }
                for row in try XCTUnwrap(pairs[pair]) {
                    let id = try XCTUnwrap(row["id"] as? String), text = try XCTUnwrap(row["source"] as? String)
                    let key = pair + "/" + id + "/" + sid, words = LocalImmersion.words(text, language: "en")
                    var outputs: [String: Any] = [:], evidence: [String: Any] = [:], steps: [[String: Any]] = []
                    for density in try XCTUnwrap(plans[key]) {
                        let limit = budget(words.count, density), bits = String(density.bitPattern, radix: 16)
                        var arms: [String: Any] = [:]
                        for arm in ["current", "candidate"] {
                            let o = try XCTUnwrap(owners[arm]), beforeDirect = ProcessInfo.processInfo.systemUptime
                            let direct = try await o.provider.resolve(.init(original: text, pair: .init(source: "en", target: target), density: density, knownConceptIDs: known))
                            let directMS = (ProcessInfo.processInfo.systemUptime - beforeDirect) * 1000, trace = o.trace()
                            let hs = try hits(o, trace: trace, words: words)
                            XCTAssertTrue(!hs.contains { $0.cost > 1 } || potential.contains(pair + "/" + id))
                            if let model = plannedHits[key + "/" + arm] {
                                XCTAssertEqual(Set(direct.partial?.references.compactMap(\.outputID) ?? []), shape(model, budget: limit))
                            }
                            XCTAssertLessThanOrEqual(direct.partial?.references.reduce(0) { $0 + $1.nativeSourceTokens } ?? 0, limit)
                            let constraints = try XCTUnwrap(direct.validated(text: text, sourceLanguage: "en", targetLanguage: target, identity: o.provider.identity))
                            if let partial = direct.partial { XCTAssertNotNil(constraints.filterPartial(partial)) }
                            let recognitions: [[String: Any]] = direct.recognitions.map { r in
                                ["rule": r.ruleID, "record": r.recordSHA256, "context": [r.context.location, NSMaxRange(r.context)],
                                 "mode": String(describing: r.mode), "mask": r.mask.map { [$0.location, NSMaxRange($0)] } as Any? ?? NSNull(),
                                 "approved": r.approvedOutputs.map { ["id": $0.outputID, "scope": [$0.range.location, NSMaxRange($0.range)]] }]
                            }
                            let ev: [String: Any] = ["trace": trace, "recognitions": recognitions]
                            let eh = JapaneseStarterLookup.digest(try encoded(ev)); evidence[eh] = ev
                            let engineKey = arm + "/" + bits
                            let engine: ConversationImmersion
                            if let existing = engines[engineKey] { engine = existing }
                            else {
                                engine = ConversationImmersion(modelStatus: { _ in .unsupported }, sourceUnits: o.provider)
                                await engine.configure(pair: .init(source: "en", target: target), density: density, knownConceptIDs: known)
                                engines[engineKey] = engine
                            }
                            engine.selectInputLanguage("en", for: id)
                            let beforeRoute = ProcessInfo.processInfo.systemUptime
                            let route = await engine.result(for: text, inputLanguage: "en", messageID: id)
                            let routeMS = (ProcessInfo.processInfo.systemUptime - beforeRoute) * 1000
                            let outcome = try XCTUnwrap(engine.lastOutcome); XCTAssertEqual(outcome.localTranslationCalls, 0)
                            let directPresentation = direct.partial.map { ImmersionPresentation.partial($0) }
                            let result: [String: Any] = ["direct_spans": spans(directPresentation), "direct_mixed": mixed(directPresentation, original: text),
                                "direct_references": references(directPresentation), "route_spans": spans(route), "route_mixed": mixed(route, original: text),
                                "route_references": references(route), "origin": outcome.origin?.rawValue as Any? ?? NSNull(), "status": outcome.status.rawValue,
                                "provider_identity": o.provider.identity, "pack_sha256": o.packSHA]
                            let oh = JapaneseStarterLookup.digest(try encoded(result)); outputs[oh] = result
                            if arm == "current", let expected = baseline[key + "/" + bits] as? [String: Any] {
                                XCTAssertEqual(try encoded(spans(directPresentation)), try encoded(XCTUnwrap(expected["direct_spans"]))); baselineDirect += 1
                                if let wanted = expected["route_spans"] { XCTAssertEqual(try encoded(spans(route)), try encoded(wanted)); baselineRoute += 1 }
                            }
                            arms[arm] = ["output": oh, "evidence": eh, "direct_ms": directMS, "route_ms": routeMS,
                                "cache_hit": outcome.cacheHit, "translation_calls": outcome.localTranslationCalls]
                            evaluations += 1
                        }
                        steps.append(["density": density, "density_bits": bits, "budget": limit, "arms": arms])
                    }
                    let record: [String: Any] = ["pair": pair, "id": id, "source": text, "stratum": row["stratum"]!,
                        "state": sid, "known_ids": knownArray, "native_words": ranges(words), "steps": steps, "outputs": outputs, "evidence": evidence]
                    output.append(try encoded(record)); output.append(10); rows += 1
                    guard output.count <= 32 * 1024 * 1024 else { throw JapaneseStarterLookup.Invalid.input }
                }
            }
        }
        XCTAssertEqual(rows, 1386); XCTAssertEqual(evaluations, plannedEvaluations)
        XCTAssertEqual(baselineDirect, 1536); XCTAssertEqual(baselineRoute, 768)
        var controls: [[String: Any]] = []
        for target in ["ja", "sw"] {
            let o = try owner(target, "candidate"), text = "My family and my family enjoy pizza."
            let known = Set(try o.entries.values.map { try XCTUnwrap($0["concept_id"] as? String) })
            let result = try await o.provider.resolve(.init(original: text, pair: .init(source: "en", target: target), density: 0.75, knownConceptIDs: known))
            XCTAssertNil(result.partial); XCTAssertFalse(result.recognitions.isEmpty)
            controls.append(["pair": "en-" + target, "all_candidate_known_empty": result.partial == nil])
        }
        let status: [String: Any] = ["complete": true, "rows": rows, "evaluations": evaluations, "planned_evaluations": plannedEvaluations,
            "baseline_direct_parity": baselineDirect, "baseline_route_parity": baselineRoute, "output_bytes": output.count,
            "boundary_sha256": JapaneseStarterLookup.digest(frozenBytes), "activated": false,
            "seconds": ProcessInfo.processInfo.systemUptime - started, "controls": controls]
        for (name, data) in [("content-output-apple.jsonl", output), ("content-status-apple.json", try encoded(status))] {
            let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.data")
            attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        }
    }
}
