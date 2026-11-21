import SwiftUI

struct RevealHintHistory: Codable, Equatable {
    private(set) var dailyCount = 0
    private var lastHintDay: Int?
    private(set) var unpromptedDays = Set<Int>()
    var dismissed = false
    var retired: Bool { dismissed || unpromptedDays.count >= 3 }

    // Convert the device's local civil date to an ordinal independent of DST duration.
    static func today(_ now: Date = Date(), timeZone: TimeZone = .current) -> Int {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let local = calendar.dateComponents([.year, .month, .day], from: now)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return Int(floor(calendar.date(from: local)!.timeIntervalSince1970 / 86_400))
    }
    mutating func offer(on day: Int) -> Bool {
        let interval = dailyCount < 21 ? 1 : 7
        guard !retired, lastHintDay.map({ day - $0 >= interval }) ?? true else { return false }
        dailyCount = min(21, dailyCount + 1); lastHintDay = day
        return true
    }
    mutating func reveal(on day: Int, prompted: Bool) {
        if !prompted && !retired { unpromptedDays.insert(day) }
    }
    static func load(_ vault: MessageVault) throws -> Self {
        let data = try vault.get("local", "reveal-hint-v1")
        return try data.map { try JSONDecoder().decode(Self.self, from: $0) } ?? Self()
    }
    static func update<T>(_ vault: MessageVault, _ change: (inout Self) -> T) throws -> T {
        try vault.transaction {
            let key = "reveal-hint-v1"
            let previous = try load(vault)
            var state = previous
            let result = change(&state)
            if state != previous { try vault.put("local", key, JSONEncoder().encode(state)) }
            return result
        }
    }
}

@MainActor @Observable final class RevealHintVisit {
    weak var vault: MessageVault?
    private(set) var offered = false
    private(set) var visible = false
    private(set) var reservedDuringReveal = false
    private var checkedDay: Int?
    private var recordedDay: Int?
    private var recalledThisVisit = false
    func check(on day: Int, quietReading: () async throws -> Void = { try await Task.sleep(for: .seconds(4)) }) async {
        guard let vault, day != checkedDay, !recalledThisVisit,
              let history = try? vault.transaction({ try RevealHintHistory.load(vault) }) else { return }
        var candidate = history
        guard candidate.offer(on: day) else { checkedDay = day; return }
        if history.dailyCount > 0 {
            do { try await quietReading() } catch { return }
        }
        guard !Task.isCancelled, !recalledThisVisit, self.vault === vault else { return }
        if (try? RevealHintHistory.update(vault, { $0.offer(on: day) })) == true {
            offered = true; visible = true
        }
        checkedDay = day
    }
    func revealed(keepSpace: Bool) {
        reservedDuringReveal = visible && keepSpace
        guard let vault else { return }
        let day = RevealHintHistory.today()
        if !offered { recalledThisVisit = true }
        if !offered, recordedDay != day {
            try? RevealHintHistory.update(vault) { $0.reveal(on: day, prompted: false) }
            recordedDay = day
        }
        visible = false
    }
    func released() { reservedDuringReveal = false }
    func dismiss() {
        guard let vault else { return }
        try? RevealHintHistory.update(vault) { $0.dismissed = true }
        visible = false
    }
}

struct ChatRevealCue: View {
    let reading: ChatReadingState
    let vault: MessageVault?
    let composing: Bool
    @Environment(\.scenePhase) private var phase
    @State private var visit = RevealHintVisit()
    @State private var owner = UUID()
    @State private var day = RevealHintHistory.today()
    private struct Opportunity: Equatable { let eligible: Bool; let day: Int; let account: UUID? }
    private var eligible: Bool {
        reading.hasVisibleTranslation && !composing && !reading.showingMeaning && phase == .active
    }
    var body: some View {
        VStack(spacing: 0) {
            if !composing && ((visit.visible && eligible) || (visit.reservedDuringReveal && reading.holding)) {
                HStack(spacing: 4) {
                    Text("Hold to see the original").font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("chat-gesture-hint")
                    Button { visit.dismiss() } label: {
                        Image(systemName: "xmark").font(.footnote).frame(width: 44, height: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityLabel("Dismiss hint")
                }
                .foregroundStyle(VipiDesign.secondary)
                .opacity(visit.visible && eligible ? 1 : 0)
                .accessibilityHidden(!visit.visible || !eligible)
                .allowsHitTesting(visit.visible && eligible)
            }
        }
        .frame(maxWidth: .infinity)
        .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { reading.setHintFrame($0, owner: owner) }
        .onAppear { visit.vault = vault; reading.revealVisit = visit; day = RevealHintHistory.today() }
        .onReceive(NotificationCenter.default.publisher(for: .NSCalendarDayChanged)) { _ in day = RevealHintHistory.today() }
        .onChange(of: phase) { _, value in if value == .active { day = RevealHintHistory.today() } }
        .task(id: Opportunity(eligible: eligible, day: day, account: vault?.account)) {
            visit.vault = vault; reading.revealVisit = visit
            if eligible { await visit.check(on: day) }
        }
        .onDisappear {
            if reading.revealVisit === visit { reading.revealVisit = nil }
            reading.removeHintFrame(owner: owner)
        }
    }
}
