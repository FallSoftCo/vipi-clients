import SwiftUI
import CryptoKit

enum HumanReportReason: String, Codable, CaseIterable, Identifiable {
    case spam, harassment, harmful, other
    var id: String { rawValue }
    var title: String { switch self { case .spam: "Spam"; case .harassment: "Harassment"; case .harmful: "Harmful content"; case .other: "Something else" } }
}
struct HumanReportBody: Codable, Equatable {
    let report_id: UUID
    let reported_user_id: UUID
    let message_id: UUID?
    let reason: HumanReportReason
    let selected_text: String?
    let consent_version: String
    enum CodingKeys: String, CodingKey { case report_id, reported_user_id, message_id, reason, selected_text, consent_version }
    func encode(to encoder: Encoder) throws {
        var value = encoder.container(keyedBy: CodingKeys.self)
        try value.encode(report_id, forKey: .report_id); try value.encode(reported_user_id, forKey: .reported_user_id)
        try value.encode(message_id, forKey: .message_id); try value.encode(reason, forKey: .reason)
        try value.encode(selected_text, forKey: .selected_text); try value.encode(consent_version, forKey: .consent_version)
    }
}
struct HumanReportReply: Decodable { let reported: Bool; let report_id: UUID }
struct SavedHumanReport: Codable {
    let key: String
    let body: HumanReportBody
    let createdAt: Date
    var reported: Bool
}
enum HumanReportStore {
    /// Called only after the explicit disclosure confirmation. The original
    /// received journal record is authoritative, never the translated rendering.
    static func prepare(vault: MessageVault, peer: UUID, message: ChatItem?, reason: HumanReportReason) throws -> SavedHumanReport {
        try vault.transaction {
            guard peer != vault.account else { throw MessageJournal.Failure.invalidMessage }
            var text: String?
            if let message {
                guard !message.outgoing, message.state != "imported", message.peer == peer,
                      let bytes = try vault.get("incoming", message.id.uuidString.lowercased()) else { throw MessageJournal.Failure.invalidMessage }
                let original = try JSONDecoder().decode(StoredChat.self, from: bytes)
                guard original.envelope.id == message.id, original.envelope.sender == peer,
                      original.envelope.recipient == vault.account, original.text == message.text,
                      !original.text.isEmpty, original.text.utf8.count <= 32768 else { throw MessageJournal.Failure.invalidMessage }
                text = original.text
            }
            // Excludes the random request ID, so reopening/retrying the same
            // confirmed report reuses its durable body after an uncertain POST.
            let semantic = HumanReportBody(report_id: UUID(uuidString: "00000000-0000-0000-0000-000000000000")!,
                reported_user_id: peer, message_id: message?.id, reason: reason, selected_text: text, consent_version: "report-v1")
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            let key = SHA256.hash(data: try encoder.encode(semantic)).map { String(format: "%02x", $0) }.joined()
            if let bytes = try vault.get("human-report", key) {
                return try JSONDecoder().decode(SavedHumanReport.self, from: bytes)
            }
            let value = SavedHumanReport(key: key, body: HumanReportBody(report_id: UUID(), reported_user_id: peer,
                message_id: message?.id, reason: reason, selected_text: text, consent_version: "report-v1"), createdAt: Date(), reported: false)
            try vault.put("human-report", key, encoder.encode(value))
            return value
        }
    }
    static func complete(vault: MessageVault, report: SavedHumanReport) throws {
        try vault.transaction {
            guard let bytes = try vault.get("human-report", report.key) else { throw MessageJournal.Failure.missingMessage }
            var saved = try JSONDecoder().decode(SavedHumanReport.self, from: bytes)
            guard saved.body == report.body else { throw MessageJournal.Failure.conflict }
            saved.reported = true
            try vault.put("human-report", report.key, JSONEncoder().encode(saved))
        }
    }
}

struct HumanReportSelection: Identifiable {
    let id = UUID()
    let message: ChatItem?
}
struct HumanReportView: View {
    @Environment(\.dismiss) private var dismiss
    let chat: ChatSession
    let peer: UUID
    let message: ChatItem?
    @State private var reason = HumanReportReason.spam
    @State private var attempted = false
    @State private var busy = false
    @State private var reported = false
    @State private var notice: String?
    var body: some View {
        NavigationStack {
            Form {
                if reported {
                    Section { Label("Report received", systemImage: "checkmark.circle") }
                    Section { Text("You can also block this person from the conversation menu.") }
                } else {
                    Section(message == nil ? "Person to report" : "Original message to share") {
                        Text(chat.name(peer))
                        if let message { Text(message.text).textSelection(.enabled).accessibilityIdentifier("human-report-original") }
                    }
                    Section("Reason") {
                        Picker("Reason", selection: $reason) {
                            ForEach(HumanReportReason.allCases) { Text(LocalizedStringKey($0.title)).tag($0) }
                        }.disabled(attempted || busy)
                    }
                    Section {
                        Text(LocalizedStringKey(message == nil
                            ? "Send this person’s account identifier and your reason to Fallible Software, Co. (FallSoft) for review. No messages are shared."
                            : "Send only the original message shown above, the account identifiers and your reason to Fallible Software, Co. (FallSoft) for review. This shares the selected text outside your encrypted chat."))
                        Text("Reports are stored encrypted for up to 30 days. A report does not automatically block anyone or guarantee a response.")
                            .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        Link("Privacy and reporting", destination: URL(string: "https://api.mambovipi.app/privacy")!)
                        Button(LocalizedStringKey(attempted ? "Retry this report" : "Send report to FallSoft")) { submit() }
                            .disabled(busy).accessibilityIdentifier("human-report-submit")
                        if busy { ProgressView("Sending report") }
                    }
                }
                if let notice { Section { Text(notice).accessibilityIdentifier("human-report-notice") } }
            }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle(message == nil ? "Report person" : "Report message").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(reported ? "Done" : "Cancel") { dismiss() }.disabled(busy) } }
                .interactiveDismissDisabled(busy)
        }
    }
    private func submit() {
        guard !busy else { return }; attempted = true; busy = true; notice = nil
        Task {
            defer { busy = false }
            do { try await chat.report(peer: peer, message: message, reason: reason); reported = true }
            catch { notice = String(localized: "We couldn’t confirm this report. Retrying sends the same report without creating a duplicate.") }
        }
    }
}
