import SwiftUI

struct SecurityNumberView: View {
    let chat: ChatSession
    let peer: UUID
    @Environment(\.dismiss) private var dismiss
    @State private var number: SecurityNumber?
    @State private var failed = false
    @State private var loading = true
    @State private var changeFailed = false
    @State private var candidate: PeerIdentityChange?
    @State private var checking = false
    @State private var confirmChange = false
    @State private var reviewNotice: String?
    private func review() {
        guard !checking else { return }; checking = true; reviewNotice = nil
        Task {
            defer { checking = false }
            do { candidate = try await chat.reviewPeerIdentity(peer) }
            catch SignalKeys.Failure.unchangedIdentity { reviewNotice = String(localized: "The current device and encryption key still match this conversation.") }
            catch { reviewNotice = String(localized: "The current keys couldn’t be checked. Your existing trust and saved messages haven’t changed.") }
        }
    }
    private func accept() {
        guard let candidate, !checking else { return }; checking = true
        Task {
            defer { checking = false }
            do {
                try await chat.acceptPeerIdentity(candidate)
                self.candidate = nil; load()
                reviewNotice = String(localized: "New keys accepted. They remain unverified until you compare the security number.")
            } catch {
                self.candidate = nil
                reviewNotice = String(localized: "The preview expired or the keys changed again. Check the current keys before deciding. Nothing was automatically trusted.")
            }
        }
    }

    init(chat: ChatSession, peer: UUID, reviewing: PeerIdentityChange? = nil) {
        self.chat = chat; self.peer = peer; _candidate = State(initialValue: reviewing)
    }

    private func load() {
        do { number = try chat.securityNumber(peer); failed = false }
        catch { number = nil; failed = true }
        loading = false
    }
    private func change(_ value: SecurityNumber) {
        do {
            try chat.setIdentityVerified(!value.verified, peer: peer, compared: value)
            changeFailed = false; load()
        } catch { changeFailed = true; load() }
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Image(systemName: "lock.shield").font(.system(size: 34)).foregroundStyle(VipiDesign.highlight)
                    Text(chat.name(peer)).font(.title2.weight(.semibold))
                    if let candidate {
                        Text("Encryption keys changed").font(.headline)
                        Text("This is the current new security number. Check with your friend over a trusted call or in person before continuing if you didn’t expect a new device.")
                        Text(candidate.number.groups.joined(separator: "  "))
                            .font(.system(.title3, design: .monospaced)).lineSpacing(12)
                            .padding(20).frame(maxWidth: .infinity).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
                            .environment(\.layoutDirection, .leftToRight).textSelection(.enabled)
                            .accessibilityIdentifier("new-security-number")
                        Text("Accepting lets new messages use these keys. It does not mark them as verified. Saved history remains; waiting messages won’t be redirected or resent.")
                            .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        Button("Accept these keys to continue") { confirmChange = true }
                            .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).disabled(checking)
                            .accessibilityIdentifier("peer-identity-accept")
                        Button("Keep current keys") { self.candidate = nil }.disabled(checking)
                    } else if loading { ProgressView("Opening encryption details") }
                    else if failed {
                        Text("Encryption details couldn’t be opened. Your verification hasn’t changed.")
                        Button("Try again", action: load)
                    } else if let number {
                        Text("Compare all 12 groups with \(chat.name(peer)) in person or over a trusted call to confirm your encryption keys match.")
                            .foregroundStyle(VipiDesign.secondary)
                        Text(number.groups.joined(separator: "  "))
                            .font(.system(.title3, design: .monospaced)).lineSpacing(12)
                            .multilineTextAlignment(.center).frame(maxWidth: .infinity)
                            .padding(20).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
                            .environment(\.layoutDirection, .leftToRight).textSelection(.enabled)
                            .accessibilityLabel("Security number")
                            .accessibilityValue(number.digits.map(String.init).joined(separator: ", "))
                            .accessibilityIdentifier("security-number")
                        if number.verified {
                            Label("You verified these keys", systemImage: "checkmark.shield")
                                .accessibilityIdentifier("identity-verified")
                            Button("Clear verification") { change(number) }.accessibilityIdentifier("identity-clear")
                        } else {
                            Text("Not yet compared").font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            Button("I compared all 12 groups") { change(number) }
                                .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).accessibilityIdentifier("identity-verify")
                        }
                        Text("If any group differs, don’t mark it as verified. A new phone or reinstalled app can change these numbers.")
                            .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        if changeFailed { Text("The keys may have changed, or your choice couldn’t be saved. Compare the current numbers again.").font(.footnote) }
                    } else {
                        Text("Exchange a message first to create this conversation’s security number.")
                            .foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("identity-not-established")
                    }
                    if candidate == nil, number != nil, chat.ready {
                        Button("Check for changed keys", action: review).disabled(checking)
                            .accessibilityIdentifier("identity-check-current")
                    }
                    if checking { ProgressView("Checking current keys") }
                    if let reviewNotice { Text(reviewNotice).font(.footnote).accessibilityIdentifier("identity-review-notice") }
                }.padding(24).frame(maxWidth: 560).frame(maxWidth: .infinity)
            }.background(VipiDesign.canvas)
                .navigationTitle("Security number").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }.tint(VipiDesign.highlight).task { load() }
            .alert("Accept the new encryption keys?", isPresented: $confirmChange) {
                Button("Cancel", role: .cancel) {}
                Button("Accept new keys", action: accept)
            } message: { Text("Future messages will use the displayed new keys. They remain unverified until you compare the security number with your friend.") }
            .interactiveDismissDisabled(checking)
    }
}
