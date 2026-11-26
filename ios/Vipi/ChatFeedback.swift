import SwiftUI

enum FundingChoice: String, Codable, CaseIterable {
    case yes, maybe, no, skip
    var label: LocalizedStringKey {
        switch self {
        case .yes: "Yes"
        case .maybe: "Not sure"
        case .no: "No"
        case .skip: "Skip"
        }
    }
}

enum ChatIntervention { case survey, review }

/// One encrypted record per account. No message IDs, text, contacts, or usage counters leave the device.
struct ChatFeedback: Codable {
    static let route = "/v1/me/surveys/private-chat-usd1-v1"
    static let minimumGap: TimeInterval = 7 * 86_400
    private(set) var sendDays = Set<Int>()
    private(set) var sends = 0
    // A bounded set of keyed digests covers only sends that advance a threshold.
    private var counted = Set<String>()
    private var historyKind = 0
    private var historyCursor: String?
    private var qualifiedForBoth: Bool { sends >= 40 && sendDays.count >= 14 }
    private(set) var surveyOffered = false
    private(set) var pending: FundingChoice?
    private var reviewed = false
    private var lastDate: Date?
    private var lastSession: UUID?

    static func load(_ vault: MessageVault) throws -> Self {
        guard let data = try vault.get("local", "chat-feedback-v1") else { return Self() }
        return try JSONDecoder().decode(Self.self, from: data)
    }
    func save(_ vault: MessageVault) throws {
        try vault.put("local", "chat-feedback-v1", JSONEncoder().encode(self))
    }
    mutating func accepted(authoredAt: Int64) {
        sends = min(40, sends + 1)
        if sendDays.count < 14 { sendDays.insert(Int(authoredAt / 86_400_000)) }
    }
    mutating func count(_ vault: MessageVault, key: String, authoredAt: Int64) -> Bool {
        let day = Int(authoredAt / 86_400_000)
        guard !qualifiedForBoth, sends < 40 || !sendDays.contains(day) else { return false }
        let fingerprint = vault.opaqueID(scope: "feedback-authored-send-v1", value: key)
        guard counted.insert(fingerprint).inserted else { return false }
        accepted(authoredAt: authoredAt)
        if qualifiedForBoth { counted.removeAll(); historyKind = 2; historyCursor = nil }
        return true
    }
    /// Advance a durable keyset cursor; imported display history has separate record types.
    static func backfillPage(_ vault: MessageVault) throws -> Bool {
        try vault.transaction {
            var state = try Self.load(vault)
            let kinds = ["outgoing", "group-message"]
            guard state.historyKind < kinds.count, !state.qualifiedForBoth else { return false }
            let kind = kinds[state.historyKind]
            let limit = 48
            let keys = try vault.pageIDs(kind, prefix: "", before: state.historyCursor, limit: limit)
            for key in keys {
                guard let data = try vault.get(kind, key) else { continue }
                if kind == "outgoing" {
                    let saved = try JSONDecoder().decode(StoredChat.self, from: data)
                    guard saved.features?.reaction == nil else { continue }
                    guard saved.envelope.sender == vault.account, saved.envelope.id.uuidString.lowercased() == key,
                          ["accepted", "delivered", "read"].contains(saved.state) else { continue }
                    _ = state.count(vault, key: kind + "/" + key, authoredAt: saved.envelope.createdAt)
                } else {
                    let saved = try JSONDecoder().decode(GroupMessage.self, from: data)
                    guard saved.features?.reaction == nil else { continue }
                    guard saved.sender == vault.account, saved.delivery == .accepted,
                          saved.groupID.uuidString.lowercased() + "/" + saved.id.uuidString.lowercased() == key else { continue }
                    _ = state.count(vault, key: kind + "/" + key, authoredAt: saved.createdAt)
                }
                if state.qualifiedForBoth { break }
            }
            if !state.qualifiedForBoth {
                if keys.count < limit { state.historyKind += 1; state.historyCursor = nil }
                else { state.historyCursor = keys.last }
            }
            try state.save(vault)
            return state.historyKind < kinds.count && !state.qualifiedForBoth
        }
    }
    func eligible(_ kind: ChatIntervention, now: Date, session: UUID) -> Bool {
        guard lastSession != session, lastDate.map({ now.timeIntervalSince($0) >= Self.minimumGap }) ?? true else { return false }
        switch kind {
        case .survey: return !surveyOffered && sends >= 20 && sendDays.count >= 7
        case .review: return !reviewed && sends >= 40 && sendDays.count >= 14
        }
    }
    mutating func claim(_ kind: ChatIntervention, now: Date, session: UUID) -> Bool {
        guard eligible(kind, now: now, session: session) else { return false }
        lastDate = now; lastSession = session
        switch kind {
        case .survey: surveyOffered = true
        case .review: reviewed = true
        }
        return true
    }
    mutating func choose(_ choice: FundingChoice) { pending = choice }
    mutating func acknowledged() { pending = nil }
}

/// Called inside the same transaction as the first accepted delivery transition.
func recordSuccessfulChatSend(_ vault: MessageVault, key: String, authoredAt: Int64) throws {
    var usage = try ChatFeedback.load(vault)
    if usage.count(vault, key: key, authoredAt: authoredAt) { try usage.save(vault) }
}

struct FundingSurveyCard: View {
    let choose: (FundingChoice) -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Would you pay US$1 a month for Vipi?")
                .font(.title3.bold()).accessibilityAddTraits(.isHeader)
            Text("We’re exploring how to fund private chats. Vipi is free today.")
                .font(.body).foregroundStyle(VipiDesign.secondary)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { answers.fixedSize(horizontal: true, vertical: false) }
                VStack(alignment: .leading, spacing: 4) { answers }
            }
            Button("Skip") { choose(.skip) }
                .frame(minHeight: 44).accessibilityIdentifier("funding-skip")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("funding-survey")
    }
    private var answers: some View {
        ForEach([FundingChoice.yes, .maybe, .no], id: \.rawValue) { choice in
            Button { choose(choice) } label: {
                Text(choice.label).padding(.horizontal, 8).frame(minHeight: 44)
            }
            .buttonStyle(.bordered).accessibilityIdentifier("funding-" + choice.rawValue)
        }
    }
}
