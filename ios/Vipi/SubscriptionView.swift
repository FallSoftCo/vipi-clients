import SwiftUI
import StoreKit

struct SubscriptionOfferView: View {
    let store: SubscriptionStore
    let plan: VipiPlan
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    private var product: Product? { store.products[plan] }
    private var access: EntitlementSnapshot.Access? { store.snapshot?.access(plan) }
    private var trial: Bool { plan == .botMini && store.introductoryEligible.contains(plan) }

    var body: some View {
        if plan == .botMini {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("vBot replies on this device, at no extra charge.").font(.title2.weight(.semibold))
                    Text("Availability and reply languages depend on your device.")
                    Text("If you already have a Bot mini subscription, manage it in the App Store. It does not cancel automatically.")
                    Link("Manage an existing Bot mini subscription", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
                        .frame(minHeight: 44)
                }.padding(24).frame(maxWidth: 560).frame(maxWidth: .infinity)
            }.background(VipiDesign.canvas).navigationTitle("vBot")
        } else { baseOffer }
    }
    private var baseOffer: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if plan == .base && !store.accessVerificationPending(.base) && !store.accessActive(.base) && access?.cardless_trial?.active == false {
                    Text("Your free Vipi access has ended. Subscribe to continue chatting.")
                        .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                    Text("You can read, back up and restore your saved history even after a subscription ends.")
                        .font(.body).fixedSize(horizontal: false, vertical: true)
                }
                if store.accessVerificationPending(plan) {
                    Label("Checking subscription access", systemImage: "clock.arrow.circlepath")
                        .foregroundStyle(VipiDesign.secondary)
                    Text("We can’t verify your subscription right now. Please try again later. Checking won’t start a new purchase.")
                    Button("Try again") { Task { await store.refresh() } }.disabled(store.loading)
                } else if store.accessActive(plan) {
                    if access?.isReviewAccess == true {
                        Label("Review access is active", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(VipiDesign.highlight)
                        Text("No subscription is required for this account.")
                    } else if plan == .base && access?.access_source == "cardless_trial" {
                        Label("Your free Vipi access is active", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(VipiDesign.highlight)
                        Text("No payment method or subscription is required for this free period.")
                        Text("When the free period ends, you can choose whether to subscribe. You won’t be charged automatically.")
                    } else {
                        Label("Your \(plan.title) subscription is active", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(VipiDesign.highlight)
                    }
                    if plan == .base, access?.access_source == "cardless_trial",
                       let trial = access?.cardless_trial, trial.active, let date = Self.date(trial.ends_at) {
                        Text("Your free access ends \(date.formatted(date: .abbreviated, time: .shortened)).")
                    } else if let end = access?.trial_ends_at, let date = Self.date(end) {
                        Text("Your free trial ends \(date.formatted(date: .long, time: .omitted)).")
                    } else if let end = access?.expires_at, let date = Self.date(end) {
                        Text("Current access lasts until \(date.formatted(date: .long, time: .omitted)).")
                    }
                    if plan == .botMini && !store.baseActive {
                        Text("Bot mini also needs active Vipi access. You can manage your plans below.")
                            .foregroundStyle(VipiDesign.secondary)
                    }
                } else if let product {
                    VStack(alignment: .leading, spacing: 12) {
                        if trial {
                            Text("One month free").font(.title2.weight(.semibold))
                            Text("Then \(product.displayPrice) per year. Renews annually until you cancel.")
                            if let date = Calendar.current.date(byAdding: .month, value: 1, to: Date()) {
                                Text("If you start today, your first annual charge is on \(date.formatted(date: .long, time: .omitted)). The App Store confirms your exact offer and dates.")
                                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            }
                        } else {
                            Text("\(product.displayPrice) per year").font(.title2.weight(.semibold))
                            if plan == .base {
                                Text("Renews annually until you cancel.")
                                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            } else {
                                Text("Renews annually until you cancel. Any available introductory offer is confirmed by the App Store.")
                                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            }
                        }
                        if plan == .botMini {
                            if let allowance = store.botAllowance, allowance.service_ready {
                                Text("Includes \(allowance.monthly_replies) vBot replies each calendar month. Unused replies don’t carry over.")
                                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            }
                            if let base = store.products[.base], base.priceFormatStyle.currencyCode == product.priceFormatStyle.currencyCode {
                                Text("At current App Store prices: Vipi \(base.displayPrice)/year + Bot mini \(product.displayPrice)/year = \((base.price + product.price).formatted(product.priceFormatStyle))/year. Each plan renews separately.")
                                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            }
                        }
                    }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
                        .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 22))
                    benefit
                    if plan == .botMini && !store.baseActive {
                        NavigationLink("See Vipi subscription") { SubscriptionOfferView(store: store, plan: .base) }
                            .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                    } else {
                        PrimaryButton(title: trial ? "Start one month free" : "Subscribe for \(product.displayPrice) a year", busy: store.busy) {
                            Task { await store.purchase(plan) }
                        }.disabled(!store.canPurchase(plan)).accessibilityIdentifier("subscription-purchase-\(plan.rawValue)")
                    }
                    if plan == .base && store.baseStoreTrialStillOffered {
                        Text("Vipi subscriptions aren’t available yet. You haven’t been enrolled.")
                            .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                    }
                    if !store.loading && (!store.purchaseReady || (plan == .botMini && !store.botServiceReady)) {
                        Text(LocalizedStringKey(plan == .botMini ? "Bot mini isn’t available to subscribe to yet. You haven’t been enrolled." : "Subscriptions aren’t available yet. You haven’t been enrolled."))
                            .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                    }
                } else if store.loading {
                    ProgressView("Loading prices…")
                        .accessibilityIdentifier("subscription-prices-loading")
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Prices aren’t available").font(.headline)
                        Text(LocalizedStringKey(plan == .base ? "Connect to the App Store to see your subscription price. You haven’t been enrolled." : "Connect to the App Store to see your price and any free trial. You haven’t been enrolled."))
                            .font(.body).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal: false, vertical: true)
                        let actions = dynamicTypeSize.isAccessibilitySize
                            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 12))
                            : AnyLayout(HStackLayout(spacing: 20))
                        actions {
                            Button { Task { await store.refresh() } } label: {
                                Text("Try again").frame(minHeight: 44).contentShape(Rectangle())
                            }.disabled(store.loading)
                            Button { Task { await store.restore() } } label: {
                                Text("Restore purchases").frame(minHeight: 44).contentShape(Rectangle())
                            }.disabled(store.busy).accessibilityIdentifier("subscription-restore")
                        }
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
                }
                if store.accessVerificationPending(plan) || store.accessActive(plan) || product == nil { benefit }
                if plan == .botMini {
                    Text("This is a separate subscription, in addition to Vipi.").font(.body)
                    Text("vBot is powered by DeepSeek. Messages you send to vBot go to Vipi and DeepSeek to generate replies. Your chats with friends are never included automatically.")
                        .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                    Text("Automated replies can be mistaken.").font(.subheadline).foregroundStyle(VipiDesign.secondary)
                }
                if let notice = store.notice { Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("subscription-notice") }
                if !store.accessVerificationPending(plan) && access?.isReviewAccess != true &&
                    ((store.accessActive(plan) && !(plan == .base && access?.access_source == "cardless_trial")) ||
                     (!store.accessActive(plan) && product != nil)) {
                    Text("Payment is charged to your Apple Account. Cancel in App Store subscriptions before renewal to avoid the next charge. Canceling does not erase your saved conversations.")
                        .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                }
                if store.accessVerificationPending(plan) || store.accessActive(plan) || product != nil {
                    Button { Task { await store.restore() } } label: {
                        Text("Restore purchases").frame(minHeight: 44).contentShape(Rectangle())
                    }.disabled(store.busy).accessibilityIdentifier("subscription-restore")
                }
                Link(destination: URL(string: "https://apps.apple.com/account/subscriptions")!) { Text("Manage App Store subscriptions").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                HStack(spacing: 24) {
                    Link(destination: URL(string: "https://api.mambovipi.app/terms")!) { Text("Terms").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                    Link(destination: URL(string: "https://api.mambovipi.app/privacy")!) { Text("Privacy").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                }.font(.subheadline)
            }.padding(20).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.clipped().background(VipiDesign.canvas).navigationTitle(plan.title).navigationBarTitleDisplayMode(.inline)
            .task { await store.refresh() }
    }
    private var benefit: some View {
        Group {
            if plan == .base {
                Text("Your messages appear in \(VipiLanguage.named(state.targetLanguage).localizedName), translated on this device.")
            } else { Text("Chat with vBot.") }
        }.font(.body).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal: false, vertical: true)
    }
    private static func date(_ value: String) -> Date? {
        let format = ISO8601DateFormatter()
        format.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return format.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
}

struct SubscriptionsView: View {
    let store: SubscriptionStore
    var body: some View {
        List {
            Section {
                ForEach([VipiPlan.base]) { plan in
                    NavigationLink { SubscriptionOfferView(store: store, plan: plan) } label: {
                        if store.accessVerificationPending(plan) {
                            LabeledContent(plan.title) { Text("Checking access").foregroundStyle(VipiDesign.secondary) }
                        } else if plan == .base && store.accessActive(.base) && store.snapshot?.base.access_source == "cardless_trial" {
                            LabeledContent(plan.title) { Text("Free access").foregroundStyle(VipiDesign.secondary) }
                        } else {
                            LabeledContent(plan.title) {
                                Text(LocalizedStringKey(store.accessActive(plan) ? "Active" : "See plan"))
                                    .foregroundStyle(VipiDesign.secondary)
                            }
                        }
                    }
                }
            } footer: {
                Group {
                    if store.snapshot?.base.isReviewAccess == true && store.snapshot?.bot_mini.isReviewAccess == true {
                        Text("Review access is active. No subscription is required for this account.")
                    } else {
                        Text("vBot runs on supported devices at no extra charge.")
                    }
                }.font(.body).foregroundStyle(VipiDesign.secondary)
            }
            Section {
                if store.snapshot?.bot_mini.expires_at != nil {
                    Link("Manage an existing Bot mini subscription", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
                }
                Button("Restore purchases") { Task { await store.restore() } }.disabled(store.busy)
                Link("Manage App Store subscriptions", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
            }
            if let notice = store.notice { Section { Text(notice).foregroundStyle(VipiDesign.secondary) } }
            if store.loading {
                Section {
                    ProgressView(LocalizedStringKey(store.accessVerificationPending(.base) || store.accessVerificationPending(.botMini)
                        ? "Checking subscription access" : "Loading prices…"))
                        .accessibilityIdentifier("subscription-prices-loading")
                }
            } else if store.catalogUnavailable {
                Section {
                    Text("The App Store couldn’t load prices. Please try again.").foregroundStyle(VipiDesign.secondary)
                    Button("Try again") { Task { await store.refresh() } }
                        .disabled(store.loading).accessibilityIdentifier("subscription-prices-retry")
                }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas)
            .navigationTitle("Subscriptions").navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(VipiDesign.canvas, for: .navigationBar).toolbarBackground(.visible, for: .navigationBar)
            .task { await store.refresh() }
    }
}
