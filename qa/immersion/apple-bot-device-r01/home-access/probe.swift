struct Access { var active: Bool; var isReviewAccess: Bool }
struct Snapshot { var base: Access; var bot_mini: Access }
struct Store { var snapshot: Snapshot? }
struct Home { var subscriptions: Store?
    var botDescription: String {
        guard let access = subscriptions?.snapshot?.bot_mini else { return "Chat with a chatbot." }
        if access.isReviewAccess { return "Chat with a chatbot. Review access is active." }
        if access.active { return "Chat with a chatbot. Bot mini access is active." }
        return "Chat with a chatbot. Requires the separate Bot mini plan."
    }
 }
let inactive=Access(active:false,isReviewAccess:false), active=Access(active:true,isReviewAccess:false), review=Access(active:true,isReviewAccess:true)
for (store, expected, offer) in [(nil as Store?, "Chat with a chatbot.",false),(Store(snapshot:nil),"Chat with a chatbot.",false),(Store(snapshot:Snapshot(base:inactive,bot_mini:inactive)),"Chat with a chatbot. Requires the separate Bot mini plan.",true),(Store(snapshot:Snapshot(base:active,bot_mini:active)),"Chat with a chatbot. Bot mini access is active.",false),(Store(snapshot:Snapshot(base:review,bot_mini:review)),"Chat with a chatbot. Review access is active.",false)] {
 precondition(Home(subscriptions:store).botDescription==expected)
 precondition((store?.snapshot?.base.active == false)==offer)
}
print("PASS five Home access states: unknown, loading, inactive, active, complimentary; no provider readiness claim")
