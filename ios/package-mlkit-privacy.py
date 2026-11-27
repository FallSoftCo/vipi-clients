#!/usr/bin/env python3
"""Preserve pinned ML Kit manifests when CocoaPods links its frameworks statically.

The SDKs already contain these manifests. CocoaPods 1.17.0 does not copy them
from the vendored static frameworks. Give each unchanged manifest a separate
resource bundle, as with the other Pods' privacy resources. Run before signing.
"""

import hashlib
import os
from pathlib import Path
import plistlib


def main():
    if os.environ.get("CONFIGURATION") == "Simulator":
        # This UI-only configuration does not link ML Kit.
        return
    if os.environ.get("CONFIGURATION") not in ("Debug", "Release"):
        raise RuntimeError("Unrecognized ML Kit build configuration")

    common = "c8a396f0eea4373773d60036f40dc5b12d84cae0e1e565030bd7b069a55e4028"
    expected = {
        "MLKitCommon": common,
        "MLKitLanguageID": common,
        "MLKitNaturalLanguage": common,
        "MLKitTranslate": "5a02b3c3de3b9a41d85520ad4be75c7b3d342db1fd6eeaac197fab1dd4b2d1e5",
    }
    pods = Path(os.environ["PODS_ROOT"])
    resources = (
        Path(os.environ["TARGET_BUILD_DIR"])
        / os.environ["UNLOCALIZED_RESOURCES_FOLDER_PATH"]
    )
    if not resources.is_dir() or resources.suffix != ".app":
        raise RuntimeError("Expected the built Vipi app resource directory")

    # Check every input before writing. Dependency upgrades must review the new
    # declarations and update these pins and release/privacy-data-inventory.json.
    manifests = {}
    for sdk, digest in expected.items():
        source = (
            pods / sdk / "Frameworks" / (sdk + ".framework") / "PrivacyInfo.xcprivacy"
        )
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError("Review changed privacy declarations for " + sdk)
        if not isinstance(plistlib.loads(raw), dict):
            raise RuntimeError("Invalid privacy manifest for " + sdk)
        manifests[sdk] = raw

    for sdk, raw in manifests.items():
        name = sdk + "_VipiPrivacy"
        bundle = resources / (name + ".bundle")
        bundle.mkdir(exist_ok=True)
        # The app's own PrivacyInfo.xcprivacy remains separate and unchanged.
        (bundle / "PrivacyInfo.xcprivacy").write_bytes(raw)
        (bundle / "Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "co.fallsoft.vipi.privacy." + sdk,
                    "CFBundleName": name,
                    "CFBundleInfoDictionaryVersion": "6.0",
                    "CFBundlePackageType": "BNDL",
                    "CFBundleShortVersionString": "1.0",
                    "CFBundleVersion": "1",
                }
            )
        )
        print("Packaged unchanged privacy manifest: " + sdk)


if __name__ == "__main__":
    main()
