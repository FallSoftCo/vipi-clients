import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import ImageIO
import AVFoundation

/// Provider URLs expire when the completion handler returns. Copy bounded input
/// into this process's temporary directory and transfer ownership to the caller.
struct ChosenMedia: Identifiable, Sendable {
    let id = UUID()
    let url: URL
    let kind: AttachmentKind
    func discard() { try? FileManager.default.removeItem(at: url) }
    static func copy(_ source: URL, kind: AttachmentKind, type: UTType) throws -> Self {
        let size = try source.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard (1...MediaCryptography.maxBytes).contains(size) else { throw MediaCryptography.Failure.tooLarge }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(type.preferredFilenameExtension ?? "bin")
        try FileManager.default.copyItem(at: source, to: url)
        do { try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path) }
        catch { try? FileManager.default.removeItem(at: url); throw error }
        return Self(url: url, kind: kind)
    }
}
struct NativeMediaPicker: UIViewControllerRepresentable {
    let camera: Bool
    let photosOnly: Bool
    var finished: (Result<ChosenMedia?, Error>) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIViewController {
        if camera && UIImagePickerController.isSourceTypeAvailable(.camera) {
            let picker = UIImagePickerController()
            picker.sourceType = .camera
            picker.mediaTypes = photosOnly ? [UTType.image.identifier] : [UTType.image.identifier, UTType.movie.identifier]
            picker.videoMaximumDuration = 175
            picker.videoQuality = .typeMedium
            picker.delegate = context.coordinator
            return picker
        }
        var config = PHPickerConfiguration()
        config.filter = photosOnly ? .images : .any(of: [.images, .videos])
        config.selectionLimit = 1
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: UIViewController, context: Context) {}
    @MainActor final class Coordinator: NSObject, PHPickerViewControllerDelegate, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let owner: NativeMediaPicker
        init(_ owner: NativeMediaPicker) { self.owner = owner }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard let provider = results.first?.itemProvider else { owner.finished(.success(nil)); return }
            let movie = provider.hasItemConformingToTypeIdentifier(UTType.movie.identifier)
            let types = provider.registeredTypeIdentifiers.compactMap { UTType($0) }
            guard let type = types.first(where: { $0.conforms(to: movie ? .movie : .image) }) else {
                owner.finished(.failure(MediaCryptography.Failure.invalidFile)); return
            }
            provider.loadFileRepresentation(forTypeIdentifier: type.identifier) { url, error in
                let value = Result<ChosenMedia?,Error> {
                    guard let url else { throw error ?? MediaCryptography.Failure.invalidFile }
                    return try ChosenMedia.copy(url, kind: movie ? .video : .photo, type: type)
                }
                Task { @MainActor in self.owner.finished(value) }
            }
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { owner.finished(.success(nil)) }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            owner.finished(Result {
                if let url = info[.mediaURL] as? URL { return try ChosenMedia.copy(url, kind: .video, type: .quickTimeMovie) }
                guard let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.85),
                      data.count <= MediaCryptography.maxBytes else { throw MediaCryptography.Failure.invalidFile }
                let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension("jpg")
                try data.write(to: url, options: [.atomic, .completeFileProtection])
                return ChosenMedia(url: url, kind: .photo)
            })
        }
    }
}
struct AvatarEditor: View {
    let chat: ChatSession
    let account: UUID
    @State private var picking = false
    @State private var editing = false
    @State private var error = false
    var body: some View {
        Button {
            if chat.avatar(account) == nil { picking = true } else { editing = true }
        } label: {
            Label("Profile photo", systemImage: "person.crop.circle")
                .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
        }
        .confirmationDialog("Profile photo", isPresented: $editing) {
            Button("Choose photo") { picking = true }
            Button("Remove photo", role: .destructive) {
                do { try chat.setAvatar(nil) } catch { self.error = true }
            }
        }
        .sheet(isPresented: $picking) {
            NativeMediaPicker(camera: false, photosOnly: true) { result in
                picking = false
                do {
                    guard let chosen = try result.get() else { return }
                    defer { chosen.discard() }
                    guard chat.profile?.id == account, let source = CGImageSourceCreateWithURL(chosen.url as CFURL, nil),
                          let thumb = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                            kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                            kCGImageSourceThumbnailMaxPixelSize: 384
                          ] as CFDictionary) else { throw MediaCryptography.Failure.invalidFile }
                    let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = true
                    let canvas = UIGraphicsImageRenderer(size: CGSize(width: 96, height: 96), format: format)
                    let jpeg = canvas.image { context in
                        UIColor.white.setFill(); context.fill(CGRect(x: 0,y: 0,width: 96,height: 96))
                        let factor = max(96 / CGFloat(thumb.width), 96 / CGFloat(thumb.height))
                        let w = CGFloat(thumb.width) * factor, h = CGFloat(thumb.height) * factor
                        UIImage(cgImage: thumb).draw(in: CGRect(x: (96-w)/2, y: (96-h)/2, width: w, height: h))
                    }
                    for quality in [0.82, 0.65, 0.48, 0.3, 0.15] {
                        if let data = jpeg.jpegData(compressionQuality: quality), data.count <= 4096 {
                            try chat.setAvatar(data); return
                        }
                    }
                    throw MediaCryptography.Failure.tooLarge
                } catch { self.error = true }
            }
        }.alert("Couldn’t update profile photo", isPresented: $error) { Button("OK") {} }
    }
}
