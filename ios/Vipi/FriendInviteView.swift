import Contacts
import ContactsUI
import MessageUI
import SwiftUI

struct PhoneInviteTarget: Identifiable, Equatable, Sendable {
    enum Channel: String, Sendable { case message, mail }
    let id: String
    let contactID: String
    let name: String
    let address: String
    let channel: Channel

    func matches(_ query: String) -> Bool {
        let term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        if term.isEmpty || name.localizedStandardContains(term) || address.localizedStandardContains(term) { return true }
        let digits = term.filter(\.isNumber)
        return channel == .message && !digits.isEmpty &&
            term.allSatisfy { $0.isNumber || "+-. ()".contains($0) } && address.filter(\.isNumber).contains(digits)
    }
}

@MainActor @Observable final class PhoneInviteContacts {
    var enabled = false
    private(set) var status: CNAuthorizationStatus = .notDetermined
    private(set) var targets: [PhoneInviteTarget] = []
    private(set) var failed = false
    private(set) var loading = false
    private var load: Task<Void, Never>?

    func clear() { load?.cancel(); targets = []; failed = false; loading = false }

    func refresh(requestPermission: Bool = false) {
        clear()
        guard enabled else { return }
        status = CNContactStore.authorizationStatus(for: .contacts)
        loading = true
        load = Task {
            defer { if !Task.isCancelled { loading = false } }
            if status == .notDetermined && requestPermission {
                _ = try? await CNContactStore().requestAccess(for: .contacts)
            }
            guard !Task.isCancelled else { return }
            status = CNContactStore.authorizationStatus(for: .contacts)
            guard status == .authorized || status == .limited else { return }
            do {
                let values = try await Self.readTargets()
                guard !Task.isCancelled, CNContactStore.authorizationStatus(for: .contacts) == status else { return }
                targets = values
            } catch { if !Task.isCancelled { failed = true } }
        }
    }

    nonisolated static func readTargets(contactID: String? = nil) async throws -> [PhoneInviteTarget] {
        let status = CNContactStore.authorizationStatus(for: .contacts)
        guard status == .authorized || status == .limited else { return [] }
        let store = CNContactStore()
        let keys: [CNKeyDescriptor] = [CNContactIdentifierKey, CNContactGivenNameKey, CNContactFamilyNameKey,
                                       CNContactPhoneNumbersKey, CNContactEmailAddressesKey] as [CNKeyDescriptor]
        let request = CNContactFetchRequest(keysToFetch: keys)
        request.sortOrder = .userDefault
        if let contactID { request.predicate = CNContact.predicateForContacts(withIdentifiers: [contactID]) }
        var targets: [PhoneInviteTarget] = []
        try store.enumerateContacts(with: request) { contact, stop in
            if Task.isCancelled { stop.pointee = true; return }
            var name = PersonNameComponents()
            name.givenName = contact.givenName; name.familyName = contact.familyName
            let display = name.formatted()
            for phone in contact.phoneNumbers where !phone.value.stringValue.isEmpty {
                targets.append(.init(id: contact.identifier + "/tel/" + phone.identifier, contactID: contact.identifier, name: display,
                                     address: phone.value.stringValue, channel: .message))
            }
            for email in contact.emailAddresses where email.value.length > 0 {
                targets.append(.init(id: contact.identifier + "/mail/" + email.identifier, contactID: contact.identifier, name: display,
                                     address: String(email.value), channel: .mail))
            }
        }
        try Task.checkCancellation()
        return targets
    }
}

struct InviteDraft: Identifiable {
    enum Channel { case message, mail, share }
    let id = UUID()
    let channel: Channel
    let body: String
    let recipient: String?

    @MainActor static func make(channel: Channel, body: String, recipient: String? = nil,
                                canMessage: Bool = MFMessageComposeViewController.canSendText(),
                                canMail: Bool = MFMailComposeViewController.canSendMail()) -> Self {
        if (channel == .message && !canMessage) || (channel == .mail && !canMail) {
            return .init(channel: .share, body: body, recipient: nil)
        }
        return .init(channel: channel, body: body, recipient: recipient)
    }
}

private struct SystemInviteComposer: UIViewControllerRepresentable {
    let draft: InviteDraft
    @Environment(\.dismiss) private var dismiss

    init(draft: InviteDraft) { self.draft = draft }
    func makeCoordinator() -> Coordinator { Coordinator { dismiss() } }
    func makeUIViewController(context: Context) -> UIViewController {
        switch draft.channel {
        case .message:
            let composer = MFMessageComposeViewController()
            composer.messageComposeDelegate = context.coordinator
            composer.recipients = draft.recipient.map { [$0] }
            composer.body = draft.body
            return composer
        case .mail:
            let composer = MFMailComposeViewController()
            composer.mailComposeDelegate = context.coordinator
            composer.setToRecipients(draft.recipient.map { [$0] })
            composer.setMessageBody(draft.body, isHTML: false)
            return composer
        case .share:
            let composer = UIActivityViewController(activityItems: [draft.body], applicationActivities: nil)
            let coordinator = context.coordinator
            composer.completionWithItemsHandler = { _, _, _, _ in coordinator.finish() }
            return composer
        }
    }
    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
    @MainActor final class Coordinator: NSObject, @preconcurrency MFMailComposeViewControllerDelegate, @preconcurrency MFMessageComposeViewControllerDelegate {
        let finish: () -> Void
        init(finish: @escaping () -> Void) { self.finish = finish }
        func messageComposeViewController(_ controller: MFMessageComposeViewController, didFinishWith result: MessageComposeResult) { finish() }
        func mailComposeController(_ controller: MFMailComposeViewController, didFinishWith result: MFMailComposeResult, error: Error?) { finish() }
    }
}

struct FriendInviteView: View {
    let username: String
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var phase
    @State private var contacts = PhoneInviteContacts()
    @State private var query = ""
    @State private var draft: InviteDraft?
    @State private var selection: Task<Void, Never>?
    @State private var choosingLimited = false
    @State private var explainingContacts = false
    private var message: String { FriendInvitation.message(username: username) }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button { draft = .make(channel: .message, body: message) } label: { Label("Messages", systemImage: "message") }
                    Button { draft = .make(channel: .mail, body: message) } label: { Label("Mail", systemImage: "envelope") }
                    ShareLink(item: message) { Label("Share", systemImage: "square.and.arrow.up") }
                }
                Section {
                    if !contacts.enabled {
                        Button("Use phone contacts") {
                            if CNContactStore.authorizationStatus(for: .contacts) == .notDetermined {
                                explainingContacts = true
                            } else {
                                contacts.enabled = true
                                contacts.refresh()
                            }
                        }.accessibilityIdentifier("invite-use-phone-contacts")
                    } else if contacts.status == .denied || contacts.status == .restricted {
                        Text("Phone contacts are unavailable. You can still share an invite.").foregroundStyle(.secondary)
                    } else if contacts.status == .authorized || contacts.status == .limited {
                        if contacts.status == .limited {
                            Button("Manage selected contacts") { choosingLimited = true }
                        }
                        TextField("Search phone contacts", text: $query)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        let matches = contacts.targets.filter { $0.matches(query) }
                        if contacts.loading { ProgressView() }
                        else if contacts.failed { Text("Phone contacts are unavailable. You can still share an invite.").foregroundStyle(.secondary) }
                        else if matches.isEmpty { Text("No matching phone contacts").foregroundStyle(.secondary) }
                        ForEach(matches) { target in
                            Button {
                                guard phase == .active, contacts.targets.contains(target),
                                      CNContactStore.authorizationStatus(for: .contacts) == contacts.status else {
                                    contacts.refresh(); return
                                }
                                selection?.cancel()
                                selection = Task {
                                    // Recheck the selected address in the current grant before handing it to iOS.
                                    let current = try? await PhoneInviteContacts.readTargets(contactID: target.contactID)
                                    guard !Task.isCancelled, phase == .active, current?.contains(target) == true else { return }
                                    draft = .make(channel: target.channel == .mail ? .mail : .message,
                                                  body: message, recipient: target.address)
                                }
                            } label: {
                                HStack {
                                    Image(systemName: target.channel == .mail ? "envelope" : "message").accessibilityHidden(true)
                                    VStack(alignment: .leading) {
                                        if !target.name.isEmpty { Text(verbatim: target.name).font(.headline) }
                                        Text(verbatim: target.address).font(.subheadline)
                                    }
                                }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                            }
                        }
                    }
                } footer: {
                    Text("Phone contacts stay on this device. Vipi saves your Vipi friends separately.")
                }
            }
            .navigationTitle("Invite a friend").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .alert("Use phone contacts", isPresented: $explainingContacts) {
                Button("Continue") {
                    contacts.enabled = true
                    contacts.refresh(requestPermission: true)
                }
            } message: {
                Text("Vipi doesn’t keep or share your address book. Choose someone on this phone to invite by text or email. You decide whether to send.")
            }
            .sheet(item: $draft) { SystemInviteComposer(draft: $0) }
            .contactAccessPicker(isPresented: $choosingLimited) { _ in contacts.refresh() }
            .onReceive(NotificationCenter.default.publisher(for: .CNContactStoreDidChange)) { _ in
                selection?.cancel()
                if phase == .active { contacts.refresh() } else { contacts.clear() }
            }
            .onChange(of: phase) { _, state in
                if state == .active { contacts.refresh() } else { selection?.cancel(); contacts.clear(); query = "" }
            }
            .onDisappear { selection?.cancel(); contacts.clear(); query = "" }
        }
    }
}
