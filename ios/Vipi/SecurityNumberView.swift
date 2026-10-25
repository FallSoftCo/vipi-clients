import SwiftUI

struct SecurityNumberView: View {
    let chat: ChatSession
    let peer: UUID
    @Environment(\.dismiss) private var dismiss
    @State private var number: SecurityNumber?
    @State private var failed = false
    @State private var loading = true
    @State private var changeFailed = false

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
                    if loading { ProgressView("Opening encryption details") }
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
                                .buttonStyle(.borderedProminent).accessibilityIdentifier("identity-verify")
                        }
                        Text("If any group differs, don’t mark it as verified. A new phone or reinstalled app can change these numbers.")
                            .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        if changeFailed { Text("The keys may have changed, or your choice couldn’t be saved. Compare the current numbers again.").font(.footnote) }
                    } else {
                        Text("Exchange a message first to create this conversation’s security number.")
                            .foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("identity-not-established")
                    }
                }.padding(24).frame(maxWidth: 560).frame(maxWidth: .infinity)
            }.background(VipiDesign.canvas)
                .navigationTitle("Verify encryption").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }.tint(VipiDesign.highlight).task { load() }
    }
}
