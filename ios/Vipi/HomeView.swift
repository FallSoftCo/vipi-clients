import SwiftUI

struct HomeView: View {
    @Environment(AppState.self) private var state
    @State private var showingSettings = false
    @State private var showingInvite = false
    @State private var query = ""
    var body: some View {
        NavigationStack {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        HStack {
                            Text("Chats").font(.system(.largeTitle, design: .serif).weight(.medium))
                            Spacer()
                            Button { showingInvite = true } label: { Image(systemName: "square.and.pencil").font(.title3).frame(width: 44, height: 44) }.accessibilityLabel("New chat")
                        }
                        VStack(alignment: .leading, spacing: 16) {
                            VipiMark(size: 54)
                            Text("Your world,\none conversation away.").font(.system(.title, design: .serif)).fixedSize(horizontal: false, vertical: true)
                            Text("Bring a friend. Make plans. Talk about your day. A little \(VipiLanguage.named(state.targetLanguage).name) will find its way in.")
                                .foregroundStyle(.secondary).lineSpacing(4)
                            PrimaryButton(title: "Start a conversation") { showingInvite = true }
                        }.padding(26).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 28))
                        NavigationLink { BotIntroductionView() } label: {
                            HStack(spacing: 16) {
                                Image(systemName: "sparkle").font(.title2).frame(width: 50, height: 50).background(VipiDesign.outgoing, in: RoundedRectangle(cornerRadius: 18))
                                VStack(alignment: .leading, spacing: 5) {
                                    Text("vBot").font(.body.weight(.semibold)).foregroundStyle(.primary)
                                    Text("A conversation whenever you feel like one.").font(.subheadline).foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            }.padding(.vertical, 12)
                        }
                    }.padding(24).frame(maxWidth: 680).frame(maxWidth: .infinity)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { HStack(spacing: 8) { VipiMark(size: 25); Text("vipi").font(.headline) } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingSettings = true } label: { Image(systemName: "person.crop.circle").font(.title3) }.accessibilityLabel("Your profile and settings")
                }
            }
            .sheet(isPresented: $showingSettings) { SettingsView() }
            .sheet(isPresented: $showingInvite) { NewChatView() }
        }
    }
}

struct NewChatView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Friend’s username", text: $username).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .onSubmit { findFriend() }
                } footer: { Text("Enter their exact Vipi username. Your phone contacts stay private.") }
                Section { Button("Find friend", action: findFriend).disabled(username.trimmingCharacters(in: .whitespaces).isEmpty) }
                if let error { Section { Text(error).foregroundStyle(.secondary) } }
            }.navigationTitle("New conversation").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
    }
    private func findFriend() { error = "We couldn’t connect. Check your connection and try again." }
}

struct BotIntroductionView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Image(systemName: "sparkle").font(.system(size: 44)).foregroundStyle(VipiDesign.highlight)
                IntroHeading(eyebrow: "Meet vBot", title: "Something\non your mind?", detail: "Talk about your day, follow a curiosity, or make a plan. vBot keeps the conversation going while your chosen language becomes more familiar.")
                Text("vBot is powered by DeepSeek. Messages in this conversation are sent to Vipi and DeepSeek to generate replies. Your conversations with friends are never included automatically.")
                    .font(.footnote).foregroundStyle(.secondary).lineSpacing(4)
                Text("Available with Bot mini").font(.subheadline.weight(.semibold))
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.background(VipiDesign.canvas).navigationTitle("vBot").navigationBarTitleDisplayMode(.inline)
    }
}

struct SettingsView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        @Bindable var state = state
        NavigationStack {
            Form {
                Section("Your immersion") {
                    LabeledContent("Language", value: VipiLanguage.named(state.targetLanguage).name)
                    VStack(alignment: .leading, spacing: 12) {
                        HStack { Text("A little or a little more"); Spacer(); Text("\(Int(state.density * 100))%").foregroundStyle(.secondary) }
                        Slider(value: $state.density, in: 0...0.75, step: 0.05).accessibilityLabel("Immersion amount")
                        Text("The amount of unfamiliar vocabulary you see. You can always reveal the original.").font(.footnote).foregroundStyle(.secondary)
                    }.padding(.vertical, 8)
                }
                Section("Make yourself at home") {
                    Picker("Appearance", selection: $state.appearance) { ForEach(AppAppearance.allCases) { Text($0.title).tag($0) } }
                }
                Section("About Vipi") {
                    Link("Privacy Policy", destination: URL(string: "https://fallsoft.co/privacy-policy")!)
                    Link("Terms of Service", destination: URL(string: "https://fallsoft.co/terms-of-service")!)
                    LabeledContent("Made by", value: "FallSoft.Co")
                }
            }.navigationTitle("Your Vipi").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
