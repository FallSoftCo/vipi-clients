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
/// Load once for all width variants of a header, including when its streak
/// changes the size of the identity being measured.
struct ConversationStreakReader<Content: View>: View {
    let vault: MessageVault?
    let scope: StreakScope
    let id: UUID
    let revision: Int
    @ViewBuilder let content: (Int) -> Content
    @Environment(\.conversationDay) private var day
    @State private var shown: Result?
    private struct Result { let account: UUID; let scope: StreakScope; let id: UUID; let day: Int64; let count: Int }
    private var count: Int {
        guard let shown, shown.account == vault?.account, shown.scope == scope, shown.id == id, shown.day == day else { return 0 }
        return shown.count
    }
    var body: some View {
        content(count)
        .task(id: "\(vault?.account.uuidString ?? "")/\(scope.rawValue)/\(id)/\(revision)/\(day)") {
            guard let vault else { shown = nil; return }
            do {
                let value = try await ConversationStreak.load(vault, scope: scope, id: id, through: day)
                try Task.checkCancellation()
                shown = Result(account: vault.account, scope: scope, id: id, day: day, count: value)
            } catch { if !Task.isCancelled { shown = nil } }
        }
    }
}

struct ConversationStreakBadge: View {
    let vault: MessageVault?
    let scope: StreakScope
    let id: UUID
    let revision: Int

    var body: some View {
        ConversationStreakReader(vault: vault, scope: scope, id: id, revision: revision) { count in
            ConversationStreakLabel(count: count, scope: scope)
        }
    }
}

struct ConversationStreakLabel: View {
    let count: Int
    let scope: StreakScope
    var headerName: String? = nil
    var avatar: ContactAvatar? = nil
    @Environment(\.locale) private var locale
    @ScaledMetric(relativeTo: .subheadline) private var size: CGFloat = 18
    @State private var explaining = false
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
                .frame(width: headerName == nil ? min(24, size) : min(16, size),
                       height: headerName == nil ? min(24, size) : min(16, size))
                .foregroundStyle(VipiDesign.accent).accessibilityHidden(true)
            Text(verbatim: number)
                .font(headerName == nil ? .subheadline.bold() : .caption.weight(.semibold))
                .monospacedDigit().foregroundStyle(headerName == nil ? VipiDesign.ink : VipiDesign.secondary)
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
                            HStack(spacing: 6) { avatar; title(name); mark }.fixedSize(horizontal: true, vertical: false)
                            HStack(spacing: 6) { title(name); mark }.fixedSize(horizontal: true, vertical: false)
                            GeometryReader { available in
                                if available.size.width < 64 {
                                    // At the smallest width, keep both the person's
                                    // initial and their streak visible on one line.
                                    HStack(spacing: 2) {
                                        title(String(name.prefix(1)))
                                        Text(verbatim: number).font(.caption.bold()).monospacedDigit()
                                    }
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.75)
                                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                                } else {
                                    HStack(spacing: 6) { title(name); mark }
                                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                                }
                            }
                            .frame(height: 44).frame(minWidth: 44)
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
    }
}
