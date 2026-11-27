#!/usr/bin/env python3
"""Build the production Android bundle with the operator's existing signing inputs."""
import argparse
import json
import os
from pathlib import Path
import re
import stat


ROOT = Path(__file__).resolve().parent.parent


def private_file(value, label):
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{label} needs an absolute file path.")
    path = Path(value)
    try:
        metadata = path.lstat()
        parent = path.parent.stat()
    except OSError:
        raise ValueError(f"{label} is unavailable.") from None
    if (
        not path.is_absolute()
        or path.resolve() != path
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise ValueError(f"{label} needs an owned mode-0600 file in an owned mode-0700 directory.")
    return path


def signing_inputs(manifest, firebase, read_passwords):
    config_path = private_file(manifest, "Signing manifest")
    try:
        config = json.loads(config_path.read_text())
        store = private_file(config["store_file"], "Upload key store")
        store_password = private_file(config["store_password_file"], "Store password input")
        key_password = private_file(config["key_password_file"], "Key password input")
        alias = config["key_alias"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeError):
        raise ValueError("The signing manifest is invalid.") from None
    if not isinstance(alias, str) or not alias or any(ord(c) < 32 for c in alias):
        raise ValueError("The upload key alias is invalid.")

    firebase = private_file(firebase, "Firebase app configuration")
    source = ROOT / "android/app/src/main/java/co/fallsoft/vipi/Authentication.kt"
    match = re.search(
        r'FALLSOFT_VIPI_PRODUCTION\("fallsoft-vipi-production", "(client_[A-Za-z0-9]+)"\)',
        source.read_text(),
    )
    if match is None:
        raise ValueError("The production client ID could not be resolved from the Android source.")

    inputs = {
        "VIPI_WORKOS_CLIENT_ID": match[1],
        "VIPI_FIREBASE_CONFIG_FILE": str(firebase),
        "VIPI_UPLOAD_STORE_FILE": str(store),
        "VIPI_UPLOAD_KEY_ALIAS": alias,
    }
    if read_passwords:
        for name, path in (
            ("VIPI_UPLOAD_STORE_PASSWORD", store_password),
            ("VIPI_UPLOAD_KEY_PASSWORD", key_password),
        ):
            try:
                value = path.read_text().rstrip("\r\n")
            except (UnicodeError, OSError):
                raise ValueError("A signing password input could not be read.") from None
            if not value or any(c in value for c in "\r\n\x00"):
                raise ValueError("A signing password input must contain one nonempty line.")
            inputs[name] = value
    return inputs


def main():
    state = Path.home() / ".local/state/vipi"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check input paths and modes only")
    parser.add_argument("--offline", action="store_true", help="Use an existing Gradle cache")
    parser.add_argument("--signing-manifest", type=Path, default=state / "android-signing-20261107/release-input-paths.json")
    parser.add_argument("--firebase-config", type=Path, default=state / "firebase-20261107/google-services.json")
    args = parser.parse_args()
    try:
        inputs = signing_inputs(args.signing_manifest, args.firebase_config, not args.check)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Android release inputs: {error if isinstance(error, ValueError) else 'a required input could not be read.'}\n")

    if args.check:
        print("Android release input files and permissions are present. Signing was not attempted.")
        return

    build = str(ROOT / "scripts/build-android.sh")
    command = [build]
    if args.offline:
        command.append("--offline")
    command.extend((":app:verifyProductionRelease", ":app:bundleRelease"))
    os.umask(0o077)
    os.execve(build, command, {**os.environ, **inputs})


if __name__ == "__main__":
    main()
