// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VipiCore",
    platforms: [.iOS(.v18), .macOS(.v15)],
    products: [.library(name: "VipiCore", targets: ["VipiCore"])],
    targets: [.target(name: "VipiCore"), .testTarget(name: "VipiCoreTests", dependencies: ["VipiCore"])]
)
