import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

// Original Vipi mark, shared with Android's adaptive vector. SVG coordinates
// are retained so both native exports use exactly the same even-odd geometry.
guard CommandLine.arguments.count == 2 else { fatalError("Provide a new PNG path") }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard !FileManager.default.fileExists(atPath: url.path) else { fatalError("Output exists") }
let size = 1024
let context = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8,
    bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
    bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
context.setFillColor(CGColor(colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!, components: [51/255, 100/255, 79/255, 1])!)
context.fill(CGRect(x: 0, y: 0, width: size, height: size))
context.translateBy(x: 0, y: 1024)
context.scaleBy(x: 1024/108, y: -1024/108)
let shape = CGMutablePath()
shape.move(to: CGPoint(x: 34, y: 27))
shape.addLine(to: CGPoint(x: 74, y: 27))
shape.addQuadCurve(to: CGPoint(x: 83, y: 36), control: CGPoint(x: 83, y: 27))
shape.addLine(to: CGPoint(x: 83, y: 65))
shape.addQuadCurve(to: CGPoint(x: 74, y: 74), control: CGPoint(x: 83, y: 74))
shape.addLine(to: CGPoint(x: 50, y: 74))
shape.addLine(to: CGPoint(x: 35, y: 85))
shape.addLine(to: CGPoint(x: 38, y: 74))
shape.addLine(to: CGPoint(x: 34, y: 74))
shape.addQuadCurve(to: CGPoint(x: 25, y: 65), control: CGPoint(x: 25, y: 74))
shape.addLine(to: CGPoint(x: 25, y: 36))
shape.addQuadCurve(to: CGPoint(x: 34, y: 27), control: CGPoint(x: 25, y: 27))
shape.closeSubpath()
shape.move(to: CGPoint(x: 39, y: 42))
for p in [CGPoint(x: 46, y: 42), CGPoint(x: 54, y: 56), CGPoint(x: 62, y: 42), CGPoint(x: 69, y: 42), CGPoint(x: 57, y: 65), CGPoint(x: 51, y: 65)] { shape.addLine(to: p) }
shape.closeSubpath()
context.addPath(shape)
context.setFillColor(CGColor(colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!, components: [222/255, 239/255, 190/255, 1])!)
context.drawPath(using: .eoFill)
let image = context.makeImage()!
let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(destination, image, nil)
guard CGImageDestinationFinalize(destination) else { fatalError("PNG export failed") }
print(url.path)
