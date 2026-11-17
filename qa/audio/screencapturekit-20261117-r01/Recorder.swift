import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import CoreGraphics

final class Sink: NSObject, SCStreamOutput {
    let url: URL
    var file: AVAudioFile?
    var samples: Int64 = 0
    var sumSquares = 0.0
    var peak = 0.0
    var clipped: Int64 = 0
    var sampleRate = 0.0
    var channelCount = 0
    init(_ url: URL) { self.url = url }
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid,
              let desc = CMSampleBufferGetFormatDescription(sampleBuffer) else { return }
        let format = AVAudioFormat(cmAudioFormatDescription: desc)
        sampleRate = format.sampleRate; channelCount = Int(format.channelCount)
        let count = CMSampleBufferGetNumSamples(sampleBuffer)
        guard count > 0, let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(count)) else { return }
        pcm.frameLength = AVAudioFrameCount(count)
        let result = CMSampleBufferCopyPCMDataIntoAudioBufferList(sampleBuffer, at: 0, frameCount: Int32(count), into: pcm.mutableAudioBufferList)
        guard result == noErr else { return }
        do {
            if file == nil { file = try AVAudioFile(forWriting: url, settings: format.settings, commonFormat: format.commonFormat, interleaved: format.isInterleaved) }
            try file?.write(from: pcm)
            if let data = pcm.floatChannelData {
                for c in 0..<Int(format.channelCount) { for f in 0..<count {
                    let v = Double(data[format.isInterleaved ? 0 : c][format.isInterleaved ? f * Int(format.channelCount) + c : f])
                    sumSquares += v*v; peak = max(peak, abs(v)); samples += 1; if abs(v) >= 0.999 { clipped += 1 }
                }}
            }
        } catch { fputs("audio write failed\n", stderr) }
    }
}
@main struct Main {
 static func main() async {
  do {
   guard CommandLine.arguments.count == 2 else { throw NSError(domain:"usage",code:1) }
   guard !FileManager.default.fileExists(atPath: CommandLine.arguments[1]) else { fputs("Output exists; refusing overwrite.\n",stderr); exit(4) }
   guard CGPreflightScreenCaptureAccess() else { fputs("Screen recording permission missing; no request made.\n",stderr); exit(2) }
   let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
   let apps = content.applications.filter { $0.bundleIdentifier == "co.fallsoft.vipi" }
   guard apps.count == 1, let display = content.displays.first else { fputs("Exact Vipi app/display not uniquely available.\n",stderr); exit(3) }
   let filter = SCContentFilter(display: display, including: apps, exceptingWindows: [])
   let config = SCStreamConfiguration(); config.capturesAudio = true; config.sampleRate = 48000; config.channelCount = 2; config.captureMicrophone = false; config.width = 2; config.height = 2
   let sink = Sink(URL(fileURLWithPath: CommandLine.arguments[1])); let stream = SCStream(filter: filter, configuration: config, delegate: nil)
   let audioQueue = DispatchQueue(label:"vipi.audio")
   try stream.addStreamOutput(sink, type: .audio, sampleHandlerQueue: audioQueue)
   try await stream.startCapture(); print("READY"); fflush(stdout)
   try await Task.sleep(nanoseconds: 15_000_000_000); try await stream.stopCapture()
   audioQueue.sync { sink.file = nil }
   let rms = sink.samples > 0 ? sqrt(sink.sumSquares / Double(sink.samples)) : 0
   print("samples=\(sink.samples) duration=\((sink.sampleRate > 0 && sink.channelCount > 0 ? Double(sink.samples)/(sink.sampleRate * Double(sink.channelCount)) : 0)) sampleRate=\(sink.sampleRate) channels=\(sink.channelCount) rms=\(rms) peak=\(sink.peak) clipped=\(sink.clipped)")
  } catch { fputs("capture setup failed: \(type(of:error))\n",stderr); exit(1) }
 }
}
