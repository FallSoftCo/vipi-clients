import SwiftUI

struct ConversationPhotoButton: View {
    let available: Bool
    let load: () async throws -> CGImage
    @Environment(\.scenePhase) private var scenePhase
    @State private var showing = false

    var body: some View {
        Button {
            showing = true
        } label: {
            Label("Open photo", systemImage: "photo")
        }
        .disabled(!available)
        .sheet(isPresented: $showing) { ConversationPhotoSheet(load: load) }
        .onChange(of: available) { _, allowed in if !allowed { showing = false } }
        .onChange(of: scenePhase) { _, phase in if phase != .active { showing = false } }
    }
}

struct ConversationPhotoSheet: View {
    let load: () async throws -> CGImage
    @Environment(\.dismiss) private var dismiss
    @State private var attempt = 0
    @State private var phase = Phase.loading
    private enum Phase {
        case loading, opened(CGImage), unavailable, tooLarge, failed
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                switch phase {
                case .loading: ProgressView("Opening photo…")
                case .opened(let image):
                    Image(image, scale: 1, label: Text("Opened photo"))
                        .resizable().scaledToFit().accessibilityIdentifier("verified-photo-image")
                case .unavailable: Text("This photo is no longer available.")
                case .tooLarge: Text("This photo is too large to open.")
                case .failed:
                    Text("Couldn’t open this photo.")
                    Button("Try again") { attempt += 1 }.buttonStyle(.bordered)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .navigationTitle("Photo").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Close") { dismiss() } }
            }
            .task(id: attempt) {
                phase = .loading
                do {
                    let image = try await load()
                    try Task.checkCancellation()
                    phase = .opened(image)
                } catch is CancellationError {} catch {
                    guard !Task.isCancelled else { return }
                    if let failure = error as? ServiceFailure, [403, 404, 410].contains(failure.status) {
                        phase = .unavailable
                    } else if error is AttachmentRepository.PhotoFailure {
                        phase = .tooLarge
                    } else {
                        phase = .failed
                    }
                }
            }
        }
    }
}
