import SwiftUI

/// Contact identity already held locally; no photo endpoint or upload is implied.
enum ContactMonogram {
    static func text(_ name:String) -> String {
        let words = name.split(whereSeparator: { $0.isWhitespace })
        guard let first = words.first?.first else { return "?" }
        return String(first) + (words.count > 1 ? words.last!.first.map(String.init) ?? "" : "")
    }
    static func colorIndex(_ peer:UUID) -> Int {
        let bytes = peer.uuid
        return Int((bytes.7 ^ bytes.15) & 3)
    }
}

struct ContactAvatar: View {
    let peer:UUID
    let name:String
    var size:CGFloat = 30
    @ScaledMetric(relativeTo:.headline) private var scale:CGFloat = 1
    private var diameter:CGFloat { min(size * scale,size * 1.45) }
    private var tint:Color { VipiPalette.avatar(ContactMonogram.colorIndex(peer)) }
    var body:some View {
        Text(ContactMonogram.text(name))
            .font(.system(size:diameter * 0.36,weight:.semibold,design:.rounded))
            .foregroundStyle(VipiDesign.ink)
            .frame(width:diameter,height:diameter)
            .background(tint,in:Circle())
            .overlay(Circle().strokeBorder(VipiDesign.bubbleBorder,lineWidth:0.75))
            .accessibilityHidden(true)
    }
}

struct MessageDeliveryMark: View {
    let state:String
    let description:String
    @Environment(\.vipiOutgoingMessage) private var outgoing
    private var doubleCheck:Bool { state == "delivered" || state == "read" }
    private var failed:Bool { ["failed","expired","unavailable","identity_changed"].contains(state) }
    var body:some View {
        Group {
            if doubleCheck {
                ZStack {
                    Image(systemName:"checkmark").offset(x:-3)
                    Image(systemName:"checkmark").offset(x:3)
                }.frame(width:22)
            } else {
                Image(systemName:state == "accepted" ? "checkmark" : failed ? "exclamationmark.circle" : state == "cancelled" ? "minus.circle" : "clock")
                    .frame(minWidth:14)
            }
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(state == "read" ? VipiDesign.messageRead(outgoing) : failed ? VipiDesign.messageFailure(outgoing) : VipiDesign.messageSecondary(outgoing))
        .accessibilityElement(children:.ignore).accessibilityLabel(description)
        .accessibilityIdentifier("message-state-"+state)
    }
}

/// Ephemeral visual presence has no message, timestamp, sound, or announcement.
struct PeerTypingBubble: View {
    var body:some View {
        HStack {
            HStack(spacing:5) {
                ForEach(0..<3) { index in
                    Circle().fill(VipiDesign.secondary).frame(width:5,height:5)
                        .opacity([0.45,0.7,0.95][index])
                }
            }.padding(.horizontal,16).frame(height:32)
                .background(VipiDesign.incomingBubble,in:RoundedRectangle(cornerRadius:16))
                .overlay(RoundedRectangle(cornerRadius:16).strokeBorder(VipiDesign.bubbleBorder,lineWidth:0.75))
            Spacer(minLength:38)
        }
        .accessibilityElement(children:.ignore).accessibilityLabel("Friend is typing")
        .accessibilityIdentifier("peer-typing-indicator")
    }
}

struct ReplyNotificationInvitation: View {
    let denied:Bool
    let busy:Bool
    let notify:()->Void
    let dismiss:()->Void
    var body:some View {
        HStack(alignment:.top,spacing:10) {
            Image(systemName:"bell.badge").font(.body).foregroundStyle(VipiDesign.highlight).padding(.top,3).accessibilityHidden(true)
            VStack(alignment:.leading,spacing:2) {
                Text("Get notified when your friend replies.").foregroundStyle(VipiDesign.ink).font(.subheadline).fixedSize(horizontal:false,vertical:true)
                HStack(spacing:16) {
                    Button(action:notify) { Text(LocalizedStringKey(denied ? "Open Settings":"Notify me")).font(.subheadline.weight(.semibold)).frame(minHeight:44) }
                        .disabled(busy).accessibilityIdentifier("reply-notification-enable")
                    Button(action:dismiss) { Text("Not now").font(.subheadline).frame(minHeight:44) }
                        .accessibilityIdentifier("reply-notification-defer")
                }
            }
            Spacer(minLength:0)
        }
        .padding(.horizontal,14).padding(.top,12).padding(.bottom,2)
        .background(VipiDesign.surface,in:RoundedRectangle(cornerRadius:16))
        .overlay(RoundedRectangle(cornerRadius:16).strokeBorder(VipiDesign.bubbleBorder,lineWidth:0.75))
        .padding(.horizontal,14).padding(.top,8)
        .accessibilityElement(children:.contain)
        .accessibilityIdentifier("reply-notification-invitation")
    }
}

/// Intersections use measured screen coordinates after safe-area/IME clipping.
enum ChatMessageVisibility {
    static func viewport(frame:CGRect,containerHeight:CGFloat,topInset:CGFloat,bottomInset:CGFloat,composer:CGRect) -> CGRect {
        guard frame.width > 0,containerHeight > 0 else { return .zero }
        // SwiftUI can report the already clipped container frame. Applying
        // ScrollGeometry's content insets again would erase its readable area.
        let clipped = abs(frame.height-containerHeight) < 1
        let top = frame.minY + (clipped ? 0:topInset)
        let bottom = min(frame.maxY - (clipped ? 0:bottomInset),composer.height > 0 ? composer.minY:frame.maxY)
        return CGRect(x:frame.minX,y:top,width:frame.width,height:max(0,bottom-top))
    }
    static func containsReadableMessage(_ frame:CGRect,in viewport:CGRect) -> Bool {
        guard frame.height > 0,viewport.height > 0 else { return false }
        let intersection = viewport.intersection(frame)
        return !intersection.isNull && intersection.height >= min(32,frame.height/2) && intersection.width >= 24
    }
}

/// Shared by the conversation and native color qualification; metadata and
/// UIKit mixed/full text receive the same explicit message context.
struct MessageBubbleSurface:ViewModifier {
    let outgoing:Bool
    @Environment(\.colorScheme) private var colorScheme
    func body(content:Content) -> some View {
        let shape = RoundedRectangle(cornerRadius:18,style:.continuous)
        let dark = colorScheme == .dark
        content.environment(\.vipiOutgoingMessage,outgoing)
            .foregroundStyle(VipiDesign.messageInk(outgoing))
            .background {
                shape.fill(outgoing ? VipiDesign.outgoingBubble:VipiDesign.incomingBubble)
                    .shadow(color:dark ? .black.opacity(0.035):VipiLightBubbleDepth.shadowColor.opacity(VipiLightBubbleDepth.shadowOpacity),
                            radius:dark ? 2:VipiLightBubbleDepth.shadowRadius,x:0,y:dark ? 1:VipiLightBubbleDepth.shadowY)
            }
            .overlay(shape.strokeBorder(dark ? VipiDesign.bubbleBorder:VipiPalette.color(outgoing ? .outgoingEdge:.incomingEdge),
                                        lineWidth:dark ? 0.75:VipiLightBubbleDepth.strokeWidth))
    }
}
