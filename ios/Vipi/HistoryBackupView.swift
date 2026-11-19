import SwiftUI
import UniformTypeIdentifiers
import UIKit

struct HistoryBackupView: View {
    let chat: ChatSession
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var account: UUID?
    init(chat: ChatSession) { self.chat = chat; _account = State(initialValue: chat.profile?.id) }
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
    @State private var attemptedValidation = false
    @State private var attemptedConfirmation = false
    private enum Field: Hashable { case password, confirmation }
    @FocusState private var focusedField: Field?
    @State private var correctionField: Field?
    @State private var correctionRevision = 0
    private var passwordValid: Bool { (try? HistoryBackupCodec.passwordBytes(password)) != nil }
    private var passwordError: String? {
        guard attemptedValidation, !passwordValid else { return nil }
        let normalized = password.precomposedStringWithCanonicalMapping
        if normalized.utf8.count > 1024 { return String(localized: "This password is too long.") }
        return String(localized: "Use at least 12 characters.")
    }
    private var confirmationError: String? {
        attemptedConfirmation && passwordValid && !restoring && password != confirmation
            ? String(localized: "The passwords don’t match.") : nil
    }

    var body: some View {
        ScrollViewReader { scroll in
        Form {
            Section {
                Text("Back up chats with friends in an encrypted file.")
            }
            Section {
                if dynamicTypeSize.isAccessibilitySize {
                    backupMode.pickerStyle(.menu)
                } else {
                    backupMode.pickerStyle(.segmented)
                }
                if restoring {
                    Button { picker = HistoryDocumentRequest(export: nil) } label: {
                        Label(selected == nil ? "Choose backup file" : "Choose a different file", systemImage: "doc")
                    }.disabled(busy).accessibilityIdentifier("history-choose-file")
                    if let selected { Text(selected.lastPathComponent).font(.body).fixedSize(horizontal: false, vertical: true) }
                }
                if verified != nil {
                    Label("Backup unlocked", systemImage: "lock.open").foregroundStyle(VipiDesign.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                    SecureField(restoring ? "Backup password" : "New backup password", text: $password, prompt: Text(LocalizedStringKey(restoring ? "Backup password" : "New backup password")).foregroundStyle(VipiDesign.secondary))
                        .textContentType(restoring ? .password : .newPassword)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .disabled(busy).accessibilityIdentifier("history-password")
                        .focused($focusedField, equals: .password)
                        .submitLabel(restoring ? .done : .next)
                        .onSubmit { if restoring { begin() } else { focusedField = .confirmation } }
                    if let passwordError {
                        Text(passwordError).foregroundStyle(VipiDesign.destructive)
                            .accessibilityIdentifier("history-password-error")
                    }
                    }.id(Field.password)
                }
                if !restoring {
                    VStack(alignment: .leading, spacing: 8) {
                    SecureField("Confirm backup password", text: $confirmation, prompt: Text("Confirm backup password").foregroundStyle(VipiDesign.secondary))
                        .textContentType(.newPassword).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .disabled(busy).accessibilityIdentifier("history-password-confirm")
                        .focused($focusedField, equals: .confirmation)
                        .submitLabel(.done).onSubmit(begin)
                    if let confirmationError {
                        Text(confirmationError).foregroundStyle(VipiDesign.destructive)
                            .accessibilityIdentifier("history-password-confirm-error")
                    }
                    }.id(Field.confirmation)
                }
            } footer: {
                Text("Use at least 12 characters. Keep this password safe. Vipi can’t recover it.").font(.body).foregroundStyle(VipiDesign.secondary)
            }
            if let verified, restoring {
                Section("Ready to restore") {
                    LabeledContent("Messages", value: verified.messages.formatted())
                    LabeledContent("Conversations", value: verified.peers.formatted())
                    Text("History will be merged with this Vipi account. Matching messages won’t be duplicated. Restored history does not verify anyone’s messaging identity.")
                        .font(.body).foregroundStyle(VipiDesign.secondary)
                    Button("Restore history", action: restore).disabled(busy).accessibilityIdentifier("history-confirm-restore")
                    Button("Choose again") { clearImport(); selected = nil }.disabled(busy)
                }
            } else {
                Section {
                    Button(restoring ? "Check backup" : "Create encrypted backup", action: begin)
                        .disabled(busy || (restoring && selected == nil))
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
                Text("Save your friend chat history in an encrypted file, wherever you choose to keep it.")
                    .font(.body).foregroundStyle(VipiDesign.secondary)
                Text("Your messaging identity and unsent messages stay on this device.")
                    .font(.body).foregroundStyle(VipiDesign.secondary)
                Text("Your saved history is yours to keep, back up and restore.")
                    .font(.body).foregroundStyle(VipiDesign.secondary)
            }
        }
        .scrollContentBackground(.hidden).background(VipiDesign.canvas)
        .navigationTitle("Chat backup").navigationBarTitleDisplayMode(.inline)
        .task(id: correctionRevision) {
            guard correctionRevision > 0, let correctionField else { return }
            // A focused field can have been scrolled offscreen. Setting the
            // same focus again does not reveal its newly inserted error row.
            // Wait for that row's layout, then show the field and its correction
            // together, including when the user submits the same error again.
            await Task.yield()
            guard !Task.isCancelled else { return }
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                scroll.scrollTo(correctionField, anchor: .top)
            }
        }
        .sheet(item: $picker, onDismiss: { removeExport() }) { request in
            HistoryDocumentPicker(request: request) { url in
                if request.export == nil {
                    clearImport(); selected = url
                } else if url != nil { notice = String(localized: "Your encrypted backup was saved. Keep its password safe.") }
                picker = nil
            }
            // Saving a backup is optional. Keep the native sheet dismissal
            // available from every folder; onDismiss removes the staged export.
        }
        .onChange(of: restoring) { _, _ in clearImport(); selected = nil; password = ""; confirmation = ""; notice = nil; attemptedValidation = false; attemptedConfirmation = false; focusedField = nil }
        .onDisappear {
            work?.cancel(); password = ""; confirmation = ""; clearImport()
            // The document picker may still be consuming the encrypted export.
            if picker == nil { removeExport() }
        }
        }
    }
    private var backupMode: some View {
        Picker("Chat backup", selection: $restoring) {
            Text("Create backup").tag(false)
            Text("Restore backup").tag(true)
        }.disabled(busy).accessibilityIdentifier("history-backup-mode")
    }
    private func begin() {
        guard !busy else { return }
        attemptedValidation = true; notice = nil
        guard passwordValid else { revealCorrection(.password); return }
        if !restoring { attemptedConfirmation = true }
        guard restoring || password == confirmation else { revealCorrection(.confirmation); return }
        guard !restoring || selected != nil else { return }
        focusedField = nil
        busy = true
        guard let account, chat.profile?.id == account else { busy = false; return }
        let password = password, selected = selected, restoring = restoring
        work = Task {
            defer { busy = false; work = nil }
            do {
                if restoring {
                    guard let selected else { return }
                    clearImport()
                    let destination = try HistoryBackupStore.temporaryURL(account: account); staged = destination
                    let result = try await chat.inspectHistory(selected: selected, password: password, staged: destination)
                    try Task.checkCancellation(); verified = result
                } else {
                    removeExport()
                    let destination = try HistoryBackupStore.exportURL(account: account); exported = destination
                    try await chat.exportHistory(password: password, to: destination)
                    try Task.checkCancellation(); picker = HistoryDocumentRequest(export: destination)
                }
            } catch {
                if !Task.isCancelled { notice = Self.explanation(error, restoring: restoring) }
                clearImport(); removeExport()
            }
        }
    }
    private func revealCorrection(_ field: Field) {
        focusedField = field
        correctionField = field
        correctionRevision += 1
    }
    private func restore() {
        guard !busy, let staged, let verified else { return }
        busy = true; notice = nil; let password = password
        work = Task {
            defer { busy = false; work = nil; clearImport() }
            do {
                let result = try await chat.importHistory(staged: staged, password: password, verified: verified)
                if result.added == 0 && result.existing > 0 {
                    notice = String(localized: "Nothing was duplicated. Already saved: \(result.existing).")
                } else if result.added == 0 {
                    notice = String(localized: "This backup contains no messages to restore.")
                } else {
                    notice = String(localized: "Restore complete. Added: \(result.added). Already saved: \(result.existing).")
                }
                self.password = ""
            } catch { if !Task.isCancelled { notice = Self.explanation(error, restoring: true) } }
        }
    }
    private func clearImport() {
        if let staged, let account { HistoryBackupStore.removeStaged(staged, account: account) }
        staged = nil; verified = nil
    }
    private func removeExport() {
        if let exported, let account { HistoryBackupStore.removeExport(exported, account: account) }
        exported = nil
    }
    static func explanation(_ error: Error, restoring: Bool) -> String {
        if let failure = error as? HistoryBackupCodec.Failure {
            switch failure {
            case .differentAccount: return String(localized: "This backup belongs to a different Vipi account. Sign in to that account to restore it.")
            case .passwordLength: return String(localized: "Use at least 12 characters.")
            case .conflict: return String(localized: "This backup conflicts with saved messages. Nothing was changed.")
            case .damaged where restoring: return String(localized: "The password is incorrect or this backup is damaged. Nothing was changed.")
            default: break
            }
        }
        if let failure = error as? ServiceFailure, failure.code == "history_busy" { return String(localized: "Your conversations are updating. Please try again in a moment.") }
        return restoring ? String(localized: "The backup couldn’t be opened or restored. Please try again.") : String(localized: "The backup couldn’t be saved. Your conversations are still here. Please try again.")
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
