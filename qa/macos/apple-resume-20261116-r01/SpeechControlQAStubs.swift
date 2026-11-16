import Foundation
import SwiftUI
struct VipiLanguage { let name:String; static func named(_ code:String)->Self { .init(name:code) } }
#if DEBUG
enum VoiceOverQualification { static func record(_ event:String,enabled:Bool,original:Bool) {} }
#endif
/// Not exercised: this standalone proof uses the native English/Japanese voices.
final class SwahiliSpeech: @unchecked Sendable {
 static let shared=SwahiliSpeech()
 static let identifier="qa-unused-swahili-stub"
 final class Job: @unchecked Sendable { func cancel() {} }
 func render(_ text:String,to url:URL,job:Job) async throws -> RenderedSpeech { throw LocalSpeechError.unavailable }
}
#if DEBUG
enum LiveImmersionQualification { static func record(_ fields:[String:Any]) {} }
#endif
