import SwiftUI

private struct StreakDayKey: EnvironmentKey {
    static var defaultValue: Int64 { ConversationStreak.today() }
}
private extension EnvironmentValues {
    var conversationDay: Int64 {
        get { self[StreakDayKey.self] }
        set { self[StreakDayKey.self] = newValue }
    }
}
struct ConversationStreakClock: ViewModifier {
    @Environment(\.scenePhase) private var phase
    @State private var day = ConversationStreak.today()
    @State private var clockChange = 0
    func body(content: Content) -> some View {
        content.environment(\.conversationDay, day)
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.significantTimeChangeNotification)) { _ in clockChange += 1 }
            .task(id: "\(phase)-\(clockChange)") {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    let now = Date()
                    day = ConversationStreak.today(now)
                    let next = TimeInterval(day + 1) * 86_400
                    do { try await Task.sleep(for: .seconds(next - now.timeIntervalSince1970)) }
                    catch { return }
                }
            }
    }
}
struct ConversationStreakBadge: View {
    let vault: MessageVault?
    let scope: StreakScope
    let id: UUID
    let revision: Int
    var headerName: String? = nil
    var avatar: ContactAvatar? = nil
    @Environment(\.conversationDay) private var day
    @Environment(\.locale) private var locale
    @ScaledMetric(relativeTo: .subheadline) private var size: CGFloat = 18
    @State private var shown: Result?
    @State private var explaining = false
    private struct Result { let account: UUID; let id: UUID; let day: Int64; let count: Int }
    private var count: Int {
        guard let shown, shown.account == vault?.account, shown.id == id, shown.day == day else { return 0 }
        return shown.count
    }
    private var number: String { count.formatted(.number.locale(locale)) }
    private var label: String {
        String(format: String(localized: "Days in a row: %@", table: "ConversationStreak"), locale: locale, number)
    }
    private var meaning: String {
        scope == .direct ? String(localized: "A day counts when you both send a message to each other and both messages are delivered. Days start at midnight UTC.", table: "ConversationStreak") :
            String(localized: "A day counts when at least two different group members send a message. Days start at midnight UTC.", table: "ConversationStreak")
    }
    private var mark: some View {
        HStack(spacing: 3) {
            Image("FriendStreakWave").renderingMode(.template).resizable().scaledToFit()
                .frame(width: min(24,size), height: min(24,size)).foregroundStyle(VipiDesign.accent).accessibilityHidden(true)
            Text(verbatim: number).font(.subheadline.bold()).monospacedDigit().foregroundStyle(VipiDesign.ink)
        }.fixedSize().accessibilityElement(children: .ignore).accessibilityLabel(label)
    }
    private func title(_ name: String) -> some View {
        Text(verbatim: name).font(.headline).foregroundStyle(VipiDesign.ink).lineLimit(1)
    }
    var body: some View {
        ZStack {
            if let name = headerName {
                if count >= 2 {
                    Button { explaining = true } label: {
                        ViewThatFits(in: .horizontal) {
                            HStack(spacing: 5) { avatar; title(name); mark }.fixedSize(horizontal: true, vertical: false)
                            HStack(spacing: 4) { title(name); mark }.fixedSize(horizontal: true, vertical: false)
                            HStack(spacing: 3) { title(name); mark }
                        }
                        .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).accessibilityLabel(Text(verbatim: name)).accessibilityValue(label).accessibilityHint(meaning)
                    .accessibilityIdentifier("streak-explanation")
                    .alert(label, isPresented: $explaining) { Button("OK", role: .cancel) {} } message: { Text(verbatim: meaning) }
                } else {
                    HStack(spacing: 6) { avatar; title(name) }
                        .accessibilityElement(children: .ignore).accessibilityLabel(Text(verbatim: name)).accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("conversation-contact-identity")
                }
            } else if count >= 2 { mark }
        }
        .task(id: "\(vault?.account.uuidString ?? "")/\(scope.rawValue)/\(id)/\(revision)/\(day)") {
            guard let vault else { shown = nil; return }
            do {
                let value = try await ConversationStreak.load(vault, scope: scope, id: id, through: day)
                try Task.checkCancellation()
                shown = Result(account: vault.account, id: id, day: day, count: value)
            } catch { if !Task.isCancelled { shown = nil } }
        }
    }
}
