import SwiftUI
import ImageIO
import AVKit

struct AttachmentComposeButton: View {
    let chat: ChatSession
    let peer: UUID
    let onOpen: () -> Void
    let onCommitted: () -> Void
    private enum Sheet: String, Identifiable { case library, camera, voice; var id: Self { self } }
    @State private var sheet: Sheet?
    @State private var picked: ChosenMedia?
    @State private var selected: ChosenMedia?
    @State private var notice: String?
    @State private var work: Task<Void, Never>?
    @State private var busy = false
    var body: some View {
        Menu {
            Button("Choose photo or video", systemImage: "photo.on.rectangle") { choose(.library) }
            Button("Camera", systemImage: "camera") { choose(.camera) }
            Button("Voice message", systemImage: "mic") { choose(.voice) }
        } label: {
            Image(systemName: "plus.circle").font(.title2).frame(minWidth: 44, minHeight: 44)
        }.accessibilityLabel("Add attachment").accessibilityIdentifier("chat-attach")
        .disabled(busy || !chat.canViewPhoto(peer: peer))
        .sheet(item: $sheet, onDismiss: {
            if let picked { selected = picked; self.picked = nil }
        }) { source in
            if source == .voice { VoiceCaptureView { handle(.success($0)) } }
            else { NativeMediaPicker(camera: source == .camera, photosOnly: false, finished: handle) }
        }
        .sheet(item: $selected, onDismiss: { work?.cancel(); busy = false }) { file in
            NavigationStack {
                VStack(spacing: 18) {
                    if file.kind == .photo, let image = preview(file.url) {
                        Image(decorative: image, scale: 1).resizable().scaledToFit()
                    } else { LocalMediaPlayer(url: file.url, video: file.kind == .video) }
                    if let notice { Text(notice).foregroundStyle(VipiDesign.destructive).font(.callout) }
                }.padding().navigationTitle("Send attachment").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { work?.cancel(); file.discard(); selected = nil } }
                    ToolbarItem(placement: .confirmationAction) { Button("Send") { submit(file) }.disabled(busy) }
                }
                .onDisappear { file.discard() }
            }.interactiveDismissDisabled(busy)
        }
        .alert("Attachment unavailable", isPresented: Binding(get: { notice != nil && selected == nil }, set: { if !$0 { notice = nil } })) {
            Button("OK") { notice = nil }
        } message: { Text(notice ?? "") }
        .onDisappear { work?.cancel(); selected?.discard(); picked?.discard() }
    }
    private func preview(_ url: URL) -> CGImage? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        return CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 1024] as CFDictionary)
    }
    private func choose(_ target: Sheet) {
        onOpen(); notice = nil; busy = true
        work = Task { @MainActor in
            defer { busy = false }
            do {
                try await chat.confirmMediaCapability(peer)
                try Task.checkCancellation()
                if target == .camera && !UIImagePickerController.isSourceTypeAvailable(.camera) {
                    notice = String(localized: "This device has no available camera."); return
                }
                sheet = target
            } catch { if !Task.isCancelled { notice = String(localized: "Attachments aren’t available for this chat right now.") } }
        }
    }
    private func handle(_ result: Result<ChosenMedia?, Error>) {
        sheet = nil
        do { picked = try result.get() }
        catch { notice = String(localized: "Choose a photo or video under 32 MB and three minutes.") }
    }
    private func submit(_ file: ChosenMedia) {
        guard !busy, let account = chat.profile?.id else { return }
        busy = true; notice = nil
        work = Task { @MainActor in
            defer { busy = false }
            do {
                try await chat.confirmMediaCapability(peer)
                let repository = try AttachmentRepository(account: account)
                let manifest = try await repository.prepare(source: file.url, kind: file.kind)
                var committed = false
                defer { if !committed { repository.discardPrepared(manifest) } }
                try Task.checkCancellation()
                guard chat.profile?.id == account, selected?.id == file.id else { throw CancellationError() }
                let caption: String = switch file.kind {
                case .photo: String(localized: "Photo"); case .video: String(localized: "Video")
                default: String(localized: "Voice message")
                }
                _ = try chat.sendAttachments(caption, peer: peer, attachments: [manifest]); committed = true
                selected = nil; onCommitted()
            } catch { if !Task.isCancelled { notice = String(localized: "Couldn’t prepare this attachment. Try again.") } }
        }
    }
}
