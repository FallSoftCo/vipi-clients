import Foundation
import SQLite3
import VipiCore
import XCTest
@testable import Vipi

final class BundledImmersionTests: XCTestCase {
    func testAppBundledCatalogAcrossAll110DirectionsAndOriginalPreservation() async throws {
        let root = try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        let index = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("catalog.json"))) as? [String: Any])
        let rows = try XCTUnwrap(index["references"] as? [[String: String]])
        let catalog = BundledImmersionCatalog(root: root)
        var pairs = Set<String>(), count = 0, selected = 0
        for row in rows {
            let pairID = try XCTUnwrap(row["pair"]), codes = pairID.split(separator: "-").map(String.init)
            let pair = TranslationPair(source: codes[0], target: codes[1])
            let original = try XCTUnwrap(row["original"]), translation = try XCTUnwrap(row["translation"])
            let reference = try await catalog.reference(original: original, pair: pair)
            XCTAssertEqual(reference, translation)
            let result = try await catalog.result(original: original, translation: translation, pair: pair, density: 1)
            XCTAssertEqual(result.original, original); XCTAssertEqual(result.translation, translation)
            XCTAssertEqual(result.speech(source: pair.source, target: pair.target, revealed: Set(result.spans.map(\.id))).map(\.text).joined(), original)
            if ["ar", "zh", "ja", "ko"].contains(pair.target) { XCTAssertTrue(result.spans.allSatisfy { $0.romanization != nil }) }
            selected += result.spans.count; count += 1; pairs.insert(pairID)
        }
        XCTAssertEqual(pairs.count, 110); XCTAssertEqual(count, 12575); XCTAssertGreaterThan(selected, 10000)
        let pair = TranslationPair(source: "en", target: "sw")
        let corrected = try await catalog.reference(original: "I am drinking water now.", pair: pair)
        XCTAssertEqual(corrected, "Ninakunywa maji sasa.")
        let differentPerson = try await catalog.reference(original: "We are drinking water now.", pair: pair)
        XCTAssertNil(differentPerson, "Never borrow an exact reference's person/tense")
        let embedded = try await catalog.result(original: "We are drinking water now.", translation: "Tunakunywa maji sasa.", pair: pair, density: 1)
        XCTAssertEqual(embedded.spans.count, 1)
        XCTAssertEqual(embedded.speech(source: "en", target: "sw").map(\.text).joined(), "We are drinking maji now.")
        let unrelated = try await catalog.result(original: "Book a room for us.", translation: "Tuwekee chumba.", pair: pair, density: 1)
        XCTAssertTrue(unrelated.spans.isEmpty)
        let paragraph = "I like music.\nI am drinking water now."
        let combined = try await catalog.reference(original: paragraph, pair: pair)
        XCTAssertEqual(combined, "Ninapenda muziki.\nNinakunywa maji sasa.")
        let unknown = try await catalog.reference(original: "I like music.\nDo not guess this sentence.", pair: pair)
        XCTAssertNil(unknown)
        let contextualPair = TranslationPair(source: "en", target: "es")
        let owned = try await catalog.result(original: "Can they bring our book?", translation: "¿Pueden traer nuestro libro?", pair: contextualPair, density: 1)
        XCTAssertEqual(owned.speech(source: "en", target: "es").map(\.text).joined(), "Can they bring our libro?")
        let office = try await catalog.result(original: "Niko ofisini.", translation: "I’m at the office.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(office.speech(source: "sw", target: "en").map(\.text).joined(), "Niko officeni.")
        let money = try await catalog.result(original: "I don’t have enough money.", translation: "Sina pesa za kutosha.", pair: .init(source: "en", target: "sw"), density: 1)
        XCTAssertEqual(money.speech(source: "en", target: "sw").map(\.text).joined(), "I don’t have enough pesa.")
        let request = try await catalog.result(original: "Natafuta hoteli karibu.", translation: "I am looking for a hotel nearby.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(request.speech(source: "sw", target: "en").map(\.text).joined(), "Natafuta hotel karibu.")
        let plural = try await catalog.result(original: "We are looking for a hotel nearby.", translation: "Tunatafuta hoteli karibu.", pair: pair, density: 1)
        XCTAssertEqual(plural.speech(source: "en", target: "sw").map(\.text).joined(), "We are looking for a hoteli nearby.")
        let ticket = try await catalog.result(original: "I need a train ticket.", translation: "Ninahitaji tiketi ya treni.", pair: pair, density: 0.25)
        XCTAssertEqual(ticket.speech(source: "en", target: "sw").map(\.text).joined(), "I need a tiketi ya treni.")
        let unsupportedNegative = try await catalog.result(original: "We are not sending an email tonight.", translation: "Hatutumi barua pepe leo usiku.", pair: pair, density: 1)
        XCTAssertEqual(unsupportedNegative.speech(source:"en",target:"sw").map(\.text).joined(),"We are not sending an barua pepe tonight.")
        let pastNeed = try await catalog.result(original: "We needed a phone charger before dinner.", translation: "Tulihitaji chaja ya simu kabla ya chakula cha jioni.", pair: pair, density: 1)
        XCTAssertEqual(pastNeed.speech(source: "en", target: "sw").map(\.text).joined(), "We needed a chaja ya simu before chakula cha jioni.")
        let help = try await catalog.result(original: "Nahitaji msaada sasa.", translation: "I need help now.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(help.speech(source: "sw", target: "en").map(\.text).joined(), "Nahitaji help sasa.")
        let address = try await catalog.result(original: "I need a memory address.", translation: "Ninahitaji anwani ya kumbukumbu.", pair: pair, density: 1)
        XCTAssertTrue(address.spans.isEmpty, "A postal-address construction cannot authorize a memory-address mapping")
        let mismatch = try await catalog.result(original: "I need food.", translation: "Ninahitaji taarifa.", pair: pair, density: 1)
        XCTAssertTrue(mismatch.spans.isEmpty, "Matching request grammar alone cannot align different nouns")
        let polite = try await catalog.result(original: "Ningependa nambari ya simu sasa.", translation: "I would like a phone number now.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(polite.speech(source: "sw", target: "en").map(\.text).joined(), "Ningependa phone number sasa.")
        let want = try await catalog.result(original: "I want water now.", translation: "Nataka maji sasa.", pair: pair, density: 1)
        XCTAssertEqual(want.speech(source: "en", target: "sw").map(\.text).joined(), "I want maji now.")
        let changedMood = try await catalog.reference(original: "I want water now.", pair: pair)
        XCTAssertNil(changedMood, "A need reference must never become the whole translation of a want sentence")
        let french = try await catalog.result(original: "Je voudrais un numéro de téléphone.", translation: "Ningependa nambari ya simu.", pair: .init(source: "fr", target: "sw"), density: 1)
        XCTAssertEqual(french.speech(source: "fr", target: "sw").map(\.text).joined(), "Je voudrais un nambari ya simu.")
        let unsupportedNeed = try await catalog.result(original: "Sihitaji maji.", translation: "I do not need water.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(unsupportedNeed.speech(source:"sw",target:"en").map(\.text).joined(),"Sihitaji water.")
        var units=0, unchanged=0
        for pairID in pairs.sorted() {
            let codes=pairID.split(separator:"-").map(String.init), unitPair=TranslationPair(source:codes[0],target:codes[1])
            var db:OpaquePointer?
            XCTAssertEqual(sqlite3_open_v2(root.appendingPathComponent(pairID+".sqlite").path,&db,SQLITE_OPEN_READONLY,nil),SQLITE_OK)
            defer { sqlite3_close(db) }
            var statement:OpaquePointer?
            XCTAssertEqual(sqlite3_prepare_v2(db,"SELECT payload FROM mappings",-1,&statement,nil),SQLITE_OK)
            defer { sqlite3_finalize(statement) }
            var status=sqlite3_step(statement)
            while status==SQLITE_ROW {
                let pointer=try XCTUnwrap(sqlite3_column_text(statement,0))
                let row=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(String(cString:pointer).utf8)) as? [String:Any])
                if row["lexical_unit"] as? Bool == true {
                    let source=try XCTUnwrap(row["source"] as? String),target=try XCTUnwrap(row["target"] as? String)
                    let result=try await catalog.result(original:source+".",translation:target+".",pair:unitPair,density:1)
                    if source.caseInsensitiveCompare(target) == .orderedSame && !["ar","zh","ja","ko"].contains(codes[1]) {
                        XCTAssertTrue(result.spans.isEmpty,"Identical written words need no artificial flip")
                        XCTAssertEqual(result.speech(source:codes[0],target:codes[1]).map(\.text).joined(),source+".")
                        unchanged+=1
                    } else {
                        XCTAssertEqual(result.spans.count,1,pairID+":"+source)
                        XCTAssertEqual(result.spans.first?.original,source)
                        XCTAssertEqual(result.speech(source:codes[0],target:codes[1]).map(\.text).joined(),target+".")
                    }
                    units+=1
                }
                status=sqlite3_step(statement)
            }
            XCTAssertEqual(status,SQLITE_DONE)
        }
        XCTAssertEqual(units,28965)
        XCTAssertEqual(unchanged,708)
        let shared=try await catalog.result(original:"Send the phone number.",translation:"Tuma nambari ya simu.",pair:pair,density:1)
        XCTAssertEqual(shared.speech(source:"en",target:"sw").map(\.text).joined(),"Send the nambari ya simu.")
        for (left,right) in [("phone numbers.","nambari ya simu."),("phone number.","ufunguo wa mlango."),
                             ("phone number; phone number.","nambari ya simu."),("phone number.","nambari yangu ya simu.")] {
            let rejected=try await catalog.result(original:left,translation:right,pair:pair,density:1)
            XCTAssertFalse(rejected.spans.contains { $0.original.contains("number") }, "No unsupported complete phone-number unit")
        }
        let existingPhone=try await catalog.result(original:"What is your phone number?",translation:"Nambari ya simu yako ni ipi?",pair:pair,density:1)
        XCTAssertEqual(existingPhone.speech(source:"en",target:"sw").map(\.text).joined(),"What is your Nambari ya simu?")
        for (left,right,expected,source,target) in [
            ("Do you like this music?","Je, unapenda muziki huu?","Do you like this muziki?","en","sw"),
            ("Hatuna pesa leo.","We have no money today.","Hatuna money today.","sw","en"),
            ("Muziki huu ni mzuri.","This music is good.","music huu ni mzuri.","sw","en")] {
            let result=try await catalog.result(original:left,translation:right,pair:.init(source:source,target:target),density:1)
            XCTAssertEqual(result.speech(source:source,target:target).map(\.text).joined(),expected)
            XCTAssertEqual(result.original,left)
        }
        let caseReference=try await catalog.reference(original:"music.",pair:pair)
        XCTAssertNil(caseReference,"Lexical case examples cannot become whole translations")
        for (left,right) in [("music and music","muziki"),("book the taxi","weka nafasi ya teksi"),
                            ("music","filamu"),("https://example.test/music","muziki")] {
            let result=try await catalog.result(original:left,translation:right,pair:pair,density:1)
            XCTAssertTrue(result.spans.isEmpty)
        }
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("bundled-immersion-017.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        try JSONSerialization.data(withJSONObject: ["pairs":pairs.count, "references":count, "spans":selected,"lexical_units":units,"unchanged_latin_forms":unchanged,
            "runtime_path":"app-bundled-native-catalog", "independent_linguistic_acceptance":false], options: [.prettyPrinted,.sortedKeys])
            .write(to: output, options: .withoutOverwriting)
    }
    func testPeopleUnitsPreserveNumberAndExcludeAmbiguousSourceForms() async throws {
        let catalog = BundledImmersionCatalog()
        let original = "I did not see the children."
        let value = try await catalog.result(original: original, translation: "Sikuwaona watoto.", pair: .init(source: "en", target: "sw"), density: 1)
        XCTAssertEqual(value.original, original)
        XCTAssertEqual(value.speech(source: "en", target: "sw").map(\.text).joined(), "I did not see the watoto.")
        let reverse = try await catalog.result(original: "Sikumwona mtoto.", translation: "I did not see the child.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(reverse.speech(source: "sw", target: "en").map(\.text).joined(), "Sikumwona child.")
        for (left, right, source, target) in [
            (original, "Sikumwona mtoto.", "en", "sw"),
            ("Mtoto.", "Children.", "sw", "en"),
            ("Personne.", "Hakuna mtu.", "fr", "sw"),
            ("هل هي أختها أم أمها؟", "Is she her sister or her mother?", "ar", "en"),
            ("عالم يدرس العالم.", "A scholar studies the world.", "ar", "en")
        ] {
            let rejected = try await catalog.result(original: left, translation: right, pair: .init(source: source, target: target), density: 1)
            XCTAssertTrue(rejected.spans.isEmpty, "Do not borrow a different number or ambiguous source noun: " + source + ":" + left)
        }
        let reference = try await catalog.reference(original: "children.", pair: .init(source: "en", target: "sw"))
        XCTAssertNil(reference, "A noun carrier is not a whole-sentence translation")
        let friends = try await catalog.result(original: "I met my friends.", translation: "Nilikutana na marafiki zangu.", pair: .init(source: "en", target: "sw"), density: 1)
        XCTAssertEqual(friends.speech(source: "en", target: "sw").map(\.text).joined(), "I met my marafiki.")
        let books = try await catalog.result(original: "Vitabu vyetu viko hapa.", translation: "Our books are here.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(books.speech(source: "sw", target: "en").map(\.text).joined(), "books vyetu viko hapa.")
        for (left, right, source, target) in [("Vitabu.", "Book.", "sw", "en"), ("She books it.", "Anaweka nafasi; vitabu viko hapa.", "en", "sw")] {
            let rejected = try await catalog.result(original: left, translation: right, pair: .init(source: source, target: target), density: 1)
            XCTAssertTrue(rejected.spans.isEmpty)
        }
    }
    @MainActor func testShortGreetingsAndNamesakeUseLocalReferencesInBothDirections() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 0.25)
        defer { owner.close() }
        for (original, expected) in [("hi", "Hujambo."), ("Thanks a lot.", "Asante sana."),
                                     ("What's up?", "Mambo vipi?")] {
            let value = await owner.result(for: original)
            XCTAssertEqual(value?.original, original)
            XCTAssertEqual(value?.translation, expected)
            XCTAssertEqual(value?.spans.count, 1, "Keep the complete conversational formula")
            XCTAssertNil(owner.request, "Known short greetings must not enqueue translation")
        }
        let reverse = await owner.result(for: "Mambo vipi?")
        XCTAssertEqual(reverse?.original, "What's up?")
        XCTAssertEqual(reverse?.translation, "Mambo vipi?")
        XCTAssertEqual(reverse?.speech(source: "en", target: "sw").map(\.text).joined(), "Mambo vipi?")
        XCTAssertNil(owner.request)
        let catalog = BundledImmersionCatalog()
        let unknown = try await catalog.reference(original: "What's up there?", pair: .init(source: "en", target: "sw"))
        XCTAssertNil(unknown, "A social greeting cannot replace an unfamiliar whole question")
        let preserved = try await catalog.result(original: "I did not say Thanks.", translation: "Sikusema Asante.",
                                                pair: .init(source: "en", target: "sw"), density: 1)
        XCTAssertEqual(preserved.speech(source: "en", target: "sw").map(\.text).joined(), "I did not say Asante.")
    }
}
