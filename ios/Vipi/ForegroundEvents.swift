import Foundation

/// A wake-up hint contains no message, sender, ciphertext or translation. The
/// ordinary authenticated inbox/receipt path remains the only delivery path.
@MainActor protocol ForegroundEventSocket: AnyObject {
    var failureCode: Int { get }
    func receiveHint() async throws
    func receiveEvent() async throws -> ChatForegroundEvent
    func refreshAuthorization() async throws
    func close()
}

extension ForegroundEventSocket {
    func receiveEvent() async throws -> ChatForegroundEvent {
        try await receiveHint()
        return .inbox
    }
}

@MainActor final class NativeEventSocket: ForegroundEventSocket {
    private let task: URLSessionWebSocketTask
    private let refresh: @MainActor () async throws -> Void
    private var heartbeat: Task<Void, Never>?
    var failureCode: Int {
        let code = task.closeCode.rawValue
        return code == 0 ? (task.response as? HTTPURLResponse)?.statusCode ?? 0 : code
    }
    init(task: URLSessionWebSocketTask, refresh: @escaping @MainActor () async throws -> Void) {
        self.task = task
        self.refresh = refresh
        task.maximumMessageSize = 512
        task.resume()
        heartbeat = Task { @MainActor [task] in
            do {
                while !Task.isCancelled {
                    try await Task.sleep(for: .seconds(25))
                    let watchdog = Task { @MainActor [task] in
                        do {
                            try await Task.sleep(for: .seconds(10))
                            task.cancel(with: .goingAway, reason: nil)
                        } catch {}
                    }
                    defer { watchdog.cancel() }
                    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                        task.sendPing { error in
                            if let error { continuation.resume(throwing: error) } else { continuation.resume() }
                        }
                    }
                }
            } catch { task.cancel(with: .goingAway, reason: nil) }
        }
    }
    func receiveHint() async throws { _ = try await receiveEvent() }
    func receiveEvent() async throws -> ChatForegroundEvent {
        let message = try await task.receive()
        guard case let .string(text) = message, let event = ChatForegroundEvent.decode(text) else {
            throw ServiceFailure(status: 0, code: "invalid_event")
        }
        return event
    }
    static func validHint(_ text: String) -> Bool {
        guard text.utf8.count <= 512,
            let values = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: String]
        else { return false }
        return values == ["event": "inbox_changed"]
    }
    func refreshAuthorization() async throws { try await refresh() }
    func close() {
        heartbeat?.cancel()
        heartbeat = nil
        task.cancel(with: .goingAway, reason: nil)
    }
}

/// Exactly one foreground connection. Cancellation is generation-bound so a
/// suspended old connection cannot update a new account or restart itself.
@MainActor final class ForegroundEvents {
    typealias Connect = @MainActor () async throws -> any ForegroundEventSocket
    private let connect: Connect
    private let hint: @MainActor () async -> Void
    private let activity: @MainActor (ChatForegroundEvent) -> Void
    private let authorizationEnded: @MainActor () -> Void
    private let sleep: @MainActor (Double) async throws -> Void
    private let jitter: @MainActor () -> Double
    private var work: Task<Void, Never>?
    private var socket: (any ForegroundEventSocket)?
    private var generation = UUID()
    private(set) var blocked = false
    init(
        connect: @escaping Connect, hint: @escaping @MainActor () async -> Void,
        activity: @escaping @MainActor (ChatForegroundEvent) -> Void = { _ in },
        authorizationEnded: @escaping @MainActor () -> Void = {},
        sleep: @escaping @MainActor (Double) async throws -> Void = { try await Task.sleep(for: .seconds($0)) },
        jitter: @escaping @MainActor () -> Double = { Double.random(in: 0...0.2) }
    ) {
        self.connect = connect
        self.hint = hint
        self.activity = activity
        self.authorizationEnded = authorizationEnded
        self.sleep = sleep
        self.jitter = jitter
    }
    func start() {
        guard work == nil, !blocked else { return }
        let id = UUID()
        generation = id
        work = Task { @MainActor [weak self] in await self?.run(id) }
    }
    func stop() {
        generation = UUID()
        work?.cancel()
        work = nil
        socket?.close()
        socket = nil
        blocked = false
    }
    private func run(_ id: UUID) async {
        var failures = 0, refreshed = false
        defer {
            if generation == id {
                socket?.close()
                socket = nil
                work = nil
            }
        }
        while generation == id && !Task.isCancelled {
            var connection: (any ForegroundEventSocket)?
            let began = ContinuousClock.now
            do {
                let value = try await connect()
                connection = value
                guard generation == id, !Task.isCancelled else {
                    value.close()
                    return
                }
                socket = value
                activity(.inbox)
                while generation == id && !Task.isCancelled {
                    let event = try await value.receiveEvent()
                    guard generation == id, !Task.isCancelled else { return }
                    refreshed = false
                    if event == .inbox { await hint() } else { activity(event) }
                }
            } catch {
                guard generation == id, !Task.isCancelled else { return }
                let code = connection?.failureCode ?? (error as? ServiceFailure)?.status ?? 0
                connection?.close()
                socket = nil
                if code == 4403 || code == 403 {
                    blocked = true
                    authorizationEnded()
                    return
                }
                if code == 4401 || code == 401 {
                    guard !refreshed, let connection else {
                        blocked = true
                        authorizationEnded()
                        return
                    }
                    do {
                        try await connection.refreshAuthorization()
                        refreshed = true
                    } catch {
                        blocked = true
                        authorizationEnded()
                        return
                    }
                } else if error is AuthenticationManager.SessionFailure {
                    blocked = true
                    authorizationEnded()
                    return
                }
                if began.duration(to: .now) >= .seconds(30) { failures = 0 }
                let delay = min(30, pow(2, Double(min(failures, 5)))) * (1 + min(0.2, max(0, jitter())))
                failures = min(failures + 1, 5)
                do { try await sleep(delay) } catch { return }
            }
        }
    }
}
