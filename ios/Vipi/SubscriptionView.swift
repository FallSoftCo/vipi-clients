import SwiftUI
import StoreKit

struct SubscriptionOfferView: View {
    let store: SubscriptionStore
    let plan: VipiPlan
    @Environment(\.dismiss) private var dismiss
    private var product: Product? { store.products[plan] }
    private var access: EntitlementSnapshot.Access? { store.snapshot?.access(plan) }
    private var trial: Bool { store.introductoryEligible.contains(plan) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VipiMark(size: 46)
                IntroHeading(eyebrow: plan == .base ? "Vipi subscription" : "Optional chatbot subscription",
                    title: plan == .base ? "Chat with friends.\nLearn words as you read." : "Chat with vBot.",
                    detail: plan == .base
                        ? "Chat with friends and see supported words and short phrases switch into your chosen language. Bot mini is a separate, optional plan."
                        : "Bot mini adds chatbot conversations with vBot to your Vipi plan. Ask a question or talk about your day. Automated replies can be mistaken.")
                if plan == .botMini {
                    Text("vBot is powered by DeepSeek. Messages you send to vBot go to Vipi and DeepSeek to generate replies. Your chats with friends are never included automatically.")
                        .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                }
                if access?.active == true {
                    Label("Your \(plan.title) subscription is active", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(VipiDesign.highlight)
                    if let end = access?.trial_ends_at, let date = Self.date(end) {
                        Text("Your free trial ends \(date.formatted(date: .long, time: .omitted)).")
                    } else if let end = access?.expires_at, let date = Self.date(end) {
                        Text("Current access lasts until \(date.formatted(date: .long, time: .omitted)).")
                    }
                    if plan == .botMini && !store.baseActive {
                        Text("Bot mini also needs an active Vipi subscription. You can manage both subscriptions below.")
                            .foregroundStyle(VipiDesign.secondary)
                    }
                } else if let product {
                    VStack(alignment: .leading, spacing: 12) {
                        if trial {
                            Text("One month free").font(.title2.weight(.semibold))
                            Text("Then \(product.displayPrice) per year. Renews annually until you cancel.")
                            if let date = Calendar.current.date(byAdding: .month, value: 1, to: Date()) {
                                Text("If you start today, your first annual charge is on \(date.formatted(date: .long, time: .omitted)). The App Store confirms your exact offer and dates.")
                                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
                            }
                        } else {
                            Text("\(product.displayPrice) per year").font(.title2.weight(.semibold))
                            Text("Renews annually until you cancel. Any available introductory offer is confirmed by the App Store.")
                                .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        }
                        if plan == .botMini {
                            Text("This is a separate subscription, in addition to Vipi.")
                            if let allowance = store.botAllowance, allowance.service_ready {
                                Text("Includes \(allowance.monthly_replies) vBot replies each calendar month. Unused replies don’t carry over.")
                                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
                            }
                            if let base = store.products[.base], base.priceFormatStyle.currencyCode == product.priceFormatStyle.currencyCode {
                                Text("At current App Store prices: Vipi \(base.displayPrice)/year + Bot mini \(product.displayPrice)/year = \((base.price + product.price).formatted(product.priceFormatStyle))/year. Each plan renews separately.")
                                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
                            }
                        }
                    }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
                        .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 22))
                    if plan == .botMini && !store.baseActive {
                        NavigationLink("See Vipi subscription") { SubscriptionOfferView(store: store, plan: .base) }
                            .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                    } else {
                        PrimaryButton(title: trial ? "Start one month free" : "Subscribe for \(product.displayPrice) a year", busy: store.busy) {
                            Task { await store.purchase(plan) }
                        }.disabled(!store.canPurchase(plan)).accessibilityIdentifier("subscription-purchase-\(plan.rawValue)")
                    }
                    if !store.loading && (!store.purchaseReady || (plan == .botMini && !store.botServiceReady)) {
                        Text(plan == .botMini ? "Bot mini isn’t available to subscribe to yet. You haven’t been enrolled." : "Subscriptions aren’t available yet. You haven’t been enrolled.")
                            .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                    }
                } else {
                    ContentUnavailableView("Prices aren’t available", systemImage: "network", description: Text("Connect to the App Store to see your price and any free trial. You haven’t been enrolled."))
                    Button("Try again") { Task { await store.refresh() } }.disabled(store.loading)
                }
                if let notice = store.notice { Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("subscription-notice") }
                Text("Payment is charged to your Apple Account. Cancel in App Store subscriptions before renewal to avoid the next charge. Canceling does not erase your saved conversations.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
                Button("Restore purchases") { Task { await store.restore() } }.disabled(store.busy)
                    .accessibilityIdentifier("subscription-restore")
                Link("Manage App Store subscriptions", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
                HStack(spacing: 24) {
                    Link("Terms", destination: URL(string: "https://api.mambovipi.app/terms")!)
                    Link("Privacy", destination: URL(string: "https://api.mambovipi.app/privacy")!)
                }.font(.footnote)
            }.padding(26).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.background(VipiDesign.canvas).navigationTitle(plan.title).navigationBarTitleDisplayMode(.inline)
            .task { await store.refresh() }
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
                ForEach(VipiPlan.allCases) { plan in
                    NavigationLink { SubscriptionOfferView(store: store, plan: plan) } label: {
                        LabeledContent(plan.title, value: store.snapshot?.access(plan).active == true ? "Active" : "See plan")
                    }
                }
            } footer: { Text("Vipi and Bot mini are separate subscriptions. You choose each one explicitly.") }
            Section {
                Button("Restore purchases") { Task { await store.restore() } }.disabled(store.busy)
                Link("Manage App Store subscriptions", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
            }
            if let notice = store.notice { Section { Text(notice).foregroundStyle(VipiDesign.secondary) } }
        }.navigationTitle("Subscriptions").task { await store.refresh() }
    }
}
