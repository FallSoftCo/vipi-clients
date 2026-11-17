import SwiftUI
import UniformTypeIdentifiers
import UIKit

struct HistoryBackupView: View {
    let chat: ChatSession
    @State private var restoring = false
    @State private var password = ""
    @State private var confirmation = ""
    @State private var selected: URL?
    @State private var staged: URL?
    @State private var exported: URL?
    @State private var verified: HistoryBackupCodec.Summary?
    @State private var picker: HistoryDocumentRequest?
    @State private var work: Task<Void, Never>?
    @State private var busy = false
    @State private var notice: String?
    private var passwordValid: Bool { (try? HistoryBackupCodec.passwordBytes(password)) != nil }

    var body: some View {
        Form {
            Section {
                Text("Save your friend chat history in an encrypted file, wherever you choose to keep it.")
                Text("Your messaging identity and unsent messages stay on this device. vBot history is not included.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
            }
            Section {
                Picker("Chat backup", selection: $restoring) {
                    Text("Create backup").tag(false)
                    Text("Restore backup").tag(true)
                }.pickerStyle(.segmented).disabled(busy)
                if restoring {
                    Button { picker = HistoryDocumentRequest(export: nil) } label: {
                        Label(selected == nil ? "Choose backup file" : "Choose a different file", systemImage: "doc")
                    }.disabled(busy).accessibilityIdentifier("history-choose-file")
                    if let selected { Text(selected.lastPathComponent).font(.footnote).lineLimit(2) }
                }
                if verified != nil {
                    Label("Backup unlocked", systemImage: "lock.open").foregroundStyle(VipiDesign.secondary)
                } else {
                    SecureField(restoring ? "Backup password" : "New backup password", text: $password)
                        .textContentType(restoring ? .password : .newPassword)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .disabled(busy).accessibilityIdentifier("history-password")
                }
                if !restoring {
                    SecureField("Confirm backup password", text: $confirmation)
                        .textContentType(.newPassword).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .disabled(busy).accessibilityIdentifier("history-password-confirm")
                }
            } footer: {
                Text("Use a long, unique passphrase of at least 12 characters. Keep it somewhere safe. Vipi cannot recover this password.")
            }
            if let verified, restoring {
                Section("Ready to restore") {
                    LabeledContent("Messages", value: verified.messages.formatted())
                    LabeledContent("Conversations", value: verified.peers.formatted())
                    Text("History will be merged with this Vipi account. Matching messages won’t be duplicated. Restored history does not verify anyone’s messaging identity.")
                        .font(.footnote).foregroundStyle(VipiDesign.secondary)
                    Button("Restore history", action: restore).disabled(busy).accessibilityIdentifier("history-confirm-restore")
                    Button("Choose again") { clearImport(); selected = nil }.disabled(busy)
                }
            } else {
                Section {
                    Button(restoring ? "Check backup" : "Create encrypted backup", action: begin)
                        .disabled(busy || !passwordValid || (restoring ? selected == nil : password != confirmation))
                        .accessibilityIdentifier("history-begin")
                }
            }
            if busy {
                Section {
                    ProgressView(restoring ? "Checking your history…" : "Encrypting your history…")
                    Button("Cancel") { work?.cancel() }
                }
            }
            if let notice { Section { Text(notice).accessibilityIdentifier("history-notice") } }
            Section {
                Text("You can read, back up and restore your saved history even after a subscription ends.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
            }
        }
        .scrollContentBackground(.hidden).background(VipiDesign.canvas)
        .navigationTitle("Chat backup").navigationBarTitleDisplayMode(.inline)
        .sheet(item: $picker, onDismiss: { removeExport() }) { request in
            HistoryDocumentPicker(request: request) { url in
                if request.export == nil {
                    clearImport(); selected = url
                } else if url != nil { notice = "Your encrypted backup was saved. Keep its password safe." }
                picker = nil
            }.interactiveDismissDisabled()
        }
        .onChange(of: restoring) { _, _ in clearImport(); selected = nil; password = ""; confirmation = ""; notice = nil }
        .onDisappear {
            work?.cancel(); password = ""; confirmation = ""; clearImport()
            // The document picker may still be consuming the encrypted export.
            if picker == nil { removeExport() }
        }
    }
    private func begin() {
        guard !busy, passwordValid else { return }
        busy = true; notice = nil
        let password = password, selected = selected, restoring = restoring
        work = Task {
            defer { busy = false; work = nil }
            do {
                if restoring {
                    guard let selected else { return }
                    clearImport()
                    let destination = try HistoryBackupStore.temporaryURL(); staged = destination
                    let result = try await chat.inspectHistory(selected: selected, password: password, staged: destination)
                    try Task.checkCancellation(); verified = result
                } else {
                    removeExport()
                    let destination = try HistoryBackupStore.exportURL(); exported = destination
                    try await chat.exportHistory(password: password, to: destination)
                    try Task.checkCancellation(); picker = HistoryDocumentRequest(export: destination)
                }
            } catch {
                if !Task.isCancelled { notice = explanation(error) }
                clearImport(); removeExport()
            }
        }
    }
    private func restore() {
        guard !busy, let staged, let verified else { return }
        busy = true; notice = nil; let password = password
        work = Task {
            defer { busy = false; work = nil; clearImport() }
            do {
                let result = try await chat.importHistory(staged: staged, password: password, verified: verified)
                if result.added == 0 && result.existing > 0 {
                    notice = result.existing == 1 ? "This message was already saved. Nothing was duplicated." : "All \(result.existing) messages were already saved. Nothing was duplicated."
                } else if result.added == 0 { notice = "This backup contains no messages to restore." }
                else {
                    notice = "Restored \(result.added) \(result.added == 1 ? "message" : "messages"). \(result.existing) matching \(result.existing == 1 ? "message was" : "messages were") already saved."
                }
                self.password = ""
            } catch { if !Task.isCancelled { notice = explanation(error) } }
        }
    }
    private func clearImport() {
        if let staged { try? FileManager.default.removeItem(at: staged) }
        staged = nil; verified = nil
    }
    private func removeExport() {
        if let exported { HistoryBackupStore.removeExport(exported) }
        exported = nil
    }
    private func explanation(_ error: Error) -> String {
        if let failure = error as? HistoryBackupCodec.Failure {
            switch failure {
            case .differentAccount: return "This backup belongs to a different Vipi account. Sign in to that account to restore it."
            case .passwordLength: return "Use a passphrase of at least 12 characters."
            case .conflict: return "This backup conflicts with saved messages. Nothing was changed."
            default: break
            }
        }
        if let failure = error as? ServiceFailure, failure.code == "history_busy" { return "Your conversations are updating. Please try again in a moment." }
        return restoring ? "The password is incorrect or this backup is damaged. Nothing was changed." : "The backup couldn’t be saved. Your conversations are still here. Please try again."
    }
}

private struct HistoryDocumentRequest: Identifiable {
    let id = UUID()
    let export: URL?
}
private struct HistoryDocumentPicker: UIViewControllerRepresentable {
    let request: HistoryDocumentRequest
    let completion: (URL?) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let view = request.export.map { UIDocumentPickerViewController(forExporting: [$0], asCopy: true) }
            ?? UIDocumentPickerViewController(forOpeningContentTypes: [.data], asCopy: false)
        view.allowsMultipleSelection = false; view.shouldShowFileExtensions = true; view.delegate = context.coordinator
        return view
    }
    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}
    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let completion: (URL?) -> Void
        init(completion: @escaping (URL?) -> Void) { self.completion = completion }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) { completion(urls.first) }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) { completion(nil) }
    }
}
