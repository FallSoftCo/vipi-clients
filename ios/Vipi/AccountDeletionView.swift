import SwiftUI

struct DeleteAccountView: View {
    let chat: ChatSession
    var closeBot: () throws -> Void = {}
    @Environment(AccountDeletion.self) private var deletion
    @State private var confirm = false
    @State private var error: String?
    var body: some View {
        Form {
            Section {
                Text("Your profile and messages waiting for delivery will be removed from Vipi. Saved chats on this device will also be erased.")
                Text("Your Fallsoft sign-in and accounts in other Fallsoft apps will remain.")
                Text("This won’t erase friends’ copies or backups you saved elsewhere.")
            } header: { Text("What will be deleted") }
            Section {
                Button("Delete Vipi account", role: .destructive) { confirm = true }.accessibilityIdentifier("delete-account")
                if let error { Text(error).font(.body) }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas)
            .navigationTitle("Delete Vipi account").navigationBarTitleDisplayMode(.inline)
            .alert("Delete your Vipi account?", isPresented: $confirm) {
                Button("Cancel", role: .cancel) {}
                Button("Delete Vipi account", role: .destructive) {
                    do {
                        guard chat.profile != nil || chat.needsProfile else { throw ServiceFailure(status: 0, code: "profile_required") }
                        let account = chat.profile?.id ?? UUID()
                        try deletion.begin(account: account, userID: chat.userID) { try closeBot(); try chat.close() }
                    } catch { self.error = String(localized: "Deletion couldn’t be prepared. Close and reopen Vipi to try again.") }
                }
            } message: { Text("Your Vipi account and chats on this device will be permanently deleted. This can’t be undone.") }
    }
}

struct AccountDeletionProgressView: View {
    @Environment(AccountDeletion.self) private var deletion
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.scenePhase) private var phase
    private var finished: Bool { deletion.pending?.phase == .completed && deletion.pending?.localErased == true }
    private var accepted: Bool { deletion.pending.map { $0.phase != .prepared } ?? false }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Image(systemName: "person.crop.circle.badge.minus").font(.system(size: 38)).foregroundStyle(VipiDesign.secondary)
                    Text(LocalizedStringKey(finished ? "Vipi account deleted" : accepted ? "Deletion requested" : "Delete your Vipi account"))
                        .font(.largeTitle.weight(.bold)).accessibilityAddTraits(.isHeader)
                    Text(LocalizedStringKey(finished ? "Your Vipi account and chats on this device have been removed." : accepted ? "Vipi has accepted your request. We’re finishing deletion. You can close the app and check back later." : "We’ll confirm the request and remove your saved chats from this device. Vipi saves your progress if the connection drops."))
                        .foregroundStyle(VipiDesign.secondary)
                    if let notice = deletion.notice { Text(notice).font(.subheadline).accessibilityIdentifier("deletion-notice") }
                    if let error = authentication.errorMessage, deletion.needsSignIn { Text(error).font(.subheadline) }
                    if deletion.busy { ProgressView("Checking deletion…") }
                    else if finished { Button("Done") { deletion.finish() }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight) }
                    else if !deletion.loadFailed {
                        if deletion.needsSignIn, let record = deletion.pending {
                            Button("Sign in to confirm") { authentication.signIn(expectedUser: record.userID) }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).disabled(authentication.busy)
                        }
                        Button(accepted ? "Check status" : "Continue deletion") { Task { await deletion.resume() } }
                            .buttonStyle(.bordered).accessibilityIdentifier("deletion-retry")
                    }
                    Text("Your Fallsoft sign-in and accounts in other Fallsoft apps will remain.")
                        .font(.body).foregroundStyle(VipiDesign.secondary)
                    Text("Friends’ copies and backups saved elsewhere remain.")
                        .font(.body).foregroundStyle(VipiDesign.secondary)
                }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
            }.background(VipiDesign.canvas)
        }
        .task { await deletion.resume() }
        .onChange(of: authentication.session?.accessToken) { _, _ in if deletion.needsSignIn { Task { await deletion.resume() } } }
        .onChange(of: phase) { _, value in if value == .active { Task { await deletion.resume() } } }
    }
}
