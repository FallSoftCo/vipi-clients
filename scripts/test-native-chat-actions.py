#!/usr/bin/env python3
"""Exercise one private Vipi conversation on the iOS simulator and Android emulator.

Supply dedicated, clean simulators with the matching debug app and tests already
installed, and the iOS VipiSimulator test bundle already built. This runner
owns a fresh loopback relay and its SSH tunnel, never a real account or device.
"""
import argparse
from contextlib import ExitStack
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4


ANDROID_PACKAGE = "co.fallsoft.vipi.sourcecontextqa"
ANDROID_TEST = "co.fallsoft.vipi.LaunchPairRelayTest#exchangeWithNativePeer"
IOS_PACKAGE = "co.fallsoft.vipi"
IOS_TEST = "VipiCryptoTests/CombinedLaunchTests/testThreeMemberMessagingAndPreview"
SOURCE = Path(__file__).resolve().parents[1]


def write_json(path, value):
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2)
        file.write("\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def checked_output(command, *, payload=None, seconds=30):
    result = subprocess.run(command, input=payload, capture_output=True, text=True, timeout=seconds)
    result.check_returncode()
    return result.stdout.strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_test(command, directory, expected):
    path = directory / "test.log"
    with path.open("x") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    require(result.returncode == 0 and expected in path.read_text(errors="replace"),
            f"Native test did not pass. Inspect {path} and the original stage intent.")


def wait_until(read, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = read()
        except (OSError, URLError):
            value = None
        if value is not None:
            return value
        time.sleep(0.25)
    raise RuntimeError("Timed out waiting for the isolated test fixture")


def stop_own_process(process):
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=20)


def ready(origin):
    with urlopen(origin + "/health/ready", timeout=1) as response:
        return True if response.status == 200 else None


class NativePair:
    def __init__(self, args):
        self.args = args
        self.run = args.run_directory.resolve()
        self.origin = f"http://127.0.0.1:{args.port}"
        self.ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", args.mac]
        self.adb = [args.adb, "-s", args.android]
        self.relay = self.run / "relay"
        self.stages = []
        self.mac_documents = ""
        self.mac_containers = set()
        self.android_inputs_written = False
        self.ios_inputs = set()

    def mac(self, command, *, payload=None):
        return checked_output(self.ssh + [shlex.join(command)], payload=payload)

    def refresh_ios_documents(self):
        container = self.mac(["xcrun", "simctl", "get_app_container", self.args.ios, IOS_PACKAGE, "data"])
        require(f"/CoreSimulator/Devices/{self.args.ios}/" in container, "Choose a dedicated iOS simulator.")
        self.mac_documents = container + "/Documents"
        self.mac_containers.add(self.mac_documents)

    def start(self, stack):
        require(re.fullmatch(r"emulator-[0-9]+", self.args.android), "Choose a dedicated Android emulator.")
        require(re.fullmatch(r"[0-9]{3}", self.args.android_run), "Android run must be three digits.")
        require(checked_output(self.adb + ["get-state"]) == "device", "Android emulator is not online.")
        self.refresh_ios_documents()
        self.mac(["mkdir", "-p", self.mac_documents])
        require(not self.mac(["find", self.mac_documents, "-maxdepth", "1", "-name", "groups-combined-*", "-print"]),
                "The iOS simulator already contains native journey inputs or results. Choose a clean simulator.")
        remote_output = self.mac(["mktemp", "-d", self.args.ios_output.rstrip("/") + "/native-chat-actions.XXXXXXXX"])
        self.mac_results = remote_output
        revision = checked_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"])
        self.revision = revision
        log = stack.enter_context((self.run / "relay.log").open("x"))
        process = subprocess.Popen(
            [self.args.backend_python, str(SOURCE / "scripts/serve-signed-native-pair.py"),
             "--launch-features", "--chat-features", "--run-directory", str(self.relay), "--source-revision", revision,
             "--port", str(self.args.port), "--seconds", "5400"], stdout=log, stderr=subprocess.STDOUT)
        stack.callback(stop_own_process, process)
        wait_until(lambda: ready(self.origin))
        route = f"127.0.0.1:{self.args.port}:127.0.0.1:{self.args.port}"
        tunnel_log = stack.enter_context((self.run / "tunnel.log").open("x"))
        tunnel = subprocess.Popen(
            ["ssh", "-NT", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ExitOnForwardFailure=yes",
             "-R", route, self.args.mac], stdout=tunnel_log, stderr=subprocess.STDOUT)
        stack.callback(stop_own_process, tunnel)
        self.mac(["curl", "--retry", "3", "--retry-connrefused", "--max-time", "3", "-fsS", self.origin + "/health/ready"])
        require(tunnel.poll() is None, "The dedicated iOS relay tunnel did not stay open.")
        port = f"tcp:{self.args.port}"
        routes = checked_output(self.adb + ["reverse", "--list"])
        require(all(port not in row.split()[1:] for row in routes.splitlines()), "Android reverse port is already in use.")
        checked_output(self.adb + ["reverse", port, port])
        stack.callback(checked_output, self.adb + ["reverse", "--remove", port])
        self.credentials = read_json(self.relay / "local-test-credentials.json")
        self.profiles = {"ios": self.credentials["ios"]["username"], "android": "vipa26native", "member": "vipm26native"}
        self.accounts = {role: self.token(role) for role in self.profiles}
        android_config = {
            "endpoint": self.origin, "ios_profile": self.profiles["ios"],
            "group_in": "Hello from iOS to both friends",
            "group_reply": "Android heard the group clearly.",
            "direct_reply": "Private hello from Android.",
            "after_removal": "Hello to the remaining member",
        }
        for role in ("android", "member"):
            android_config[role] = {**self.accounts[role], "profile": self.profiles[role], "storage": uuid4().hex}
        self.android_shell_write("files/launch-pair.json", android_config)

    def remove_inputs(self):
        paths = sorted(f"{directory}/{name}" for directory in self.mac_containers for name in self.ios_inputs)
        if paths:
            self.mac(["rm", "-f", *paths])
        if self.android_inputs_written:
            checked_output(self.adb + ["shell", "run-as", ANDROID_PACKAGE, "rm", "-f", "files/launch-pair.json"])

    def token(self, role):
        identity = self.credentials[role]
        request = Request(self.origin + "/qa-auth/token",
                          data=json.dumps({key: identity[key] for key in ("username", "password")}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            token = json.load(response)
        require(token["subject"] == identity["subject"], "Unexpected local identity.")
        return {"subject": token["subject"], "access_token": token["access_token"]}

    def android_shell_write(self, path, value):
        # The application sees this private input through run-as. Clock and
        # storage identifiers are scoped to this run; an existing input is held.
        command = f"umask 077; mkdir -p files && set -C && cat > {shlex.quote(path)}"
        checked_output(self.adb + ["shell", "-T", "run-as", ANDROID_PACKAGE, "sh", "-c", shlex.quote(command)],
                       payload=json.dumps(value, ensure_ascii=True))
        self.android_inputs_written = True

    def ios_input(self, name, value, *, replace=False):
        filename = f"groups-combined-{name}.json"
        path = f"{self.mac_documents}/{filename}"
        # The initial clean-simulator check means the only replaceable inputs are
        # the values written by this process to the selected application's sandbox.
        mode = "set +C" if replace and filename in self.ios_inputs else "set -C"
        checked_output(self.ssh + [f"umask 077; {mode}; cat > {shlex.quote(path)}"],
                       payload=json.dumps(value, ensure_ascii=True))
        self.ios_inputs.add(filename)

    def stage(self, label):
        directory = self.run / label
        directory.mkdir(mode=0o700)
        write_json(directory / "intent.json", {"started": datetime.now(UTC).isoformat(), "stage": label})
        print(f"Running {label}", flush=True)
        return directory

    def finish_stage(self, directory, receipt):
        write_json(directory / "receipt.json", receipt)
        self.stages.append(directory.name)
        return receipt

    def ios(self, name, *, fixture=None, action=None, label=None):
        label = label or name
        directory = self.stage(f"ios-{label}")
        self.ios_input("config", {
            "endpoint": self.origin,
            "account": {**self.accounts["ios"], "username": self.profiles["ios"], "display_name": "iOS launch QA"},
            "stage": name, "android": self.profiles["android"], "member": self.profiles["member"],
            **({"action": {**action, "receipt": label}} if action is not None else {}),
        }, replace=True)
        if fixture is not None:
            self.ios_input(f"{name}-input", fixture)
        command = ["xcodebuild", "-workspace", self.args.workspace, "-scheme", "VipiSimulator",
                   "-configuration", "Simulator", "-destination", f"platform=iOS Simulator,id={self.args.ios}",
                   "-derivedDataPath", self.args.derived_data, "-jobs", "2", "-parallel-testing-enabled", "NO",
                   "-resultBundlePath", f"{self.mac_results}/{label}.xcresult",
                   f"-only-testing:{IOS_TEST}", "test-without-building"]
        try:
            run_test(self.ssh + [shlex.join(command)], directory, "** TEST EXECUTE SUCCEEDED **")
        finally:
            # XCTest may reinstall the hosted app and relocate its data.
            self.refresh_ios_documents()
        receipt = self.mac(["cat", f"{self.mac_documents}/groups-combined-{label}.json"])
        return self.finish_stage(directory, json.loads(receipt))

    def android(self, role, name, *, label=None, **values):
        label = label or name
        directory = self.stage(f"{role}-{label}")
        opts = {"class": ANDROID_TEST, "vipiLaunchPair": "true", "vipiDedicatedEmulator": "true",
                "vipiJourneyRun": self.args.android_run, "stage": name, "role": role, **values}
        args = [part for key, value in opts.items() for part in ("-e", key, str(value))]
        command = ["am", "instrument", "-w", "-r", *args,
                   ANDROID_PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner"]
        run_test(self.adb + ["shell", shlex.join(command)], directory, "OK (1 test)")
        path = f"files/journey-ui-{self.args.android_run}/launch-pair-{role}-{label}/receipt.json"
        receipt = checked_output(self.adb + ["exec-out", "run-as", ANDROID_PACKAGE, "cat", path])
        return self.finish_stage(directory, json.loads(receipt))

    def preview_ticket(self, device, since):
        def find():
            path = self.relay / "push-events.jsonl"
            if not path.is_file():
                return None
            events = [event for event in map(json.loads, path.read_text().splitlines())
                      if event["provider"] == "apns" and event["device_id"] == device
                      and event["preview"] and datetime.fromisoformat(event["sent_at"]) >= since]
            require(len(events) <= 1, "Unexpected duplicate APNs capture.")
            return events[0]["preview"] if events else None
        return wait_until(find)


def chat_actions(pair, conversation, ios, android, baseline_direct, baseline_group):
    direct = {"scope": "direct", "target": baseline_direct["sent"], "target_sender": android["account"]}
    sent = pair.ios("action-send", label="direct-reply-preview",
                    action={**direct, "text": "See https://example.com/", "excerpt": "Private hello from Android."})
    received = pair.android("android", "action-receive", label="action-receive-direct", operation="direct",
                            **conversation, scope="direct", targetId=direct["target"],
                            targetSender=direct["target_sender"], messageId=sent["event"])
    require(received["received"] == sent["event"], "Android received the wrong direct reply.")
    direct_target = {"scope": "direct", "target": sent["event"], "target_sender": ios["account"]}
    for sequence, emoji in enumerate(("👍", "❤️", None), 1):
        operation = f"direct-{sequence}"
        reaction = pair.android("android", "reaction-set", label=f"reaction-set-{operation}", operation=operation,
                                **conversation, scope="direct", targetId=direct_target["target"],
                                targetSender=direct_target["target_sender"], sequence=sequence, emoji=emoji or "clear")
        observed = pair.ios("reaction-observe", label=f"reaction-observe-{operation}",
                            action={**direct_target, "event": reaction["sent"], "sequence": sequence, "emoji": emoji})
        require(observed["actor"] == android["account"] and int(observed["sequence"]) == sequence,
                "iOS observed the wrong direct reaction.")

    group_reply = pair.android("android", "action-send", label="action-send-group", operation="group",
                               **conversation, scope="group", targetId=baseline_group["message"], targetSender=ios["account"])
    group = {"scope": "group", "target": baseline_group["message"], "target_sender": ios["account"]}
    apple = pair.ios("action-receive", label="group-reply-preview",
                     action={**group, "event": group_reply["sent"], "excerpt": "Hello from iOS to both friends"})
    require(apple["event"] == group_reply["sent"], "iOS received the wrong group reply.")
    member = pair.android("member", "action-receive", label="action-receive-group", operation="group",
                          **conversation, scope="group", targetId=group["target"], targetSender=group["target_sender"],
                          messageId=group_reply["sent"], eventSender=android["account"])
    require(member["received"] == group_reply["sent"], "The third member received a different logical reply.")

    group_target = {"scope": "group", "target": group_reply["sent"], "target_sender": android["account"]}
    for sequence, emoji in enumerate(("❤️", None), 1):
        group_reaction(pair, conversation, ios, group_target, sequence, emoji, ("android", "member"))
    return group_target


def group_reaction(pair, conversation, ios, target, sequence, emoji, recipients):
    operation = f"group-{sequence}"
    sent = pair.ios("reaction-set", label=f"reaction-set-{operation}",
                    action={**target, "sequence": sequence, "emoji": emoji})
    for role in recipients:
        observed = pair.android(role, "reaction-observe", label=f"reaction-observe-{operation}", operation=operation,
                                **conversation, scope="group", targetId=target["target"],
                                targetSender=target["target_sender"], actor=ios["account"],
                                sequence=sequence, emoji=emoji or "clear")
        require(int(observed["sequence"]) == sequence and observed["emoji"] == emoji,
                f"The {role} saw an unexpected group reaction.")
    return sent["event"]


def journey(pair):
    ios = pair.ios("profile")
    android = pair.android("android", "register")
    member = pair.android("member", "register")
    require(len({ios["account"], android["account"], member["account"]}) == 3, "Fixture reused an account.")
    pair.ios("signed-invitation")
    invited = pair.ios("invite")
    conversation = {"group": invited["group"], "peer": ios["account"]}
    pair.android("android", "photo", **conversation, photoMessage=invited["photo"], photoSHA=invited["photo_sha256"])
    pair.android("android", "accept", **conversation)
    pair.ios("approve-android")
    pair.android("android", "bootstrap", **conversation)
    pair.android("member", "accept", **conversation)
    original = pair.ios("approve-member")
    greeting = pair.ios("introduce-member")
    pair.android("member", "bootstrap-after-contact", **conversation, introductionMessage=greeting["message"])
    pair.android("member", "group-receive", **conversation, groupMessage=original["message"])
    # The third device pins Android's Signal identity through an ordinary
    # direct message before it can authenticate a group reply from Android.
    pair.android("android", "direct-introduction", **conversation,
                 directPeer=member["account"], directProfile=pair.profiles["member"])
    group_reply = pair.android("android", "group-reply", **conversation, groupMessage=original["message"])
    verified = pair.ios("verify")
    require(verified["group_reply"] == group_reply["sent"], "iOS received the wrong group message.")
    since = datetime.now(UTC)
    direct = pair.android("android", "direct-reply", **conversation)
    ticket = pair.preview_ticket(ios["device"], since)
    preview = pair.ios("preview", fixture={"message": direct["sent"], "ticket": ticket})
    require(preview["message"] == direct["sent"], "The notification must preview the actual direct message.")
    voice = pair.android("android", "voice", **conversation)
    pair.ios("voice", fixture={"message": voice["sent"], "sha256": voice["sha256"]})

    target = chat_actions(pair, conversation, ios, android, direct, original)

    removed = pair.ios("remove")
    final_reaction = group_reaction(pair, conversation, ios, target, 3, "👍", ("android",))
    pair.android("android", "remaining-member", **conversation, groupMessage=removed["message"])
    pair.android("member", "departed-member", **conversation, groupMessage=removed["message"],
                 scope="group", targetId=target["target"], targetSender=target["target_sender"],
                 actor=ios["account"], sequence=2, emoji="clear")
    return final_reaction, android["account"]


def relay_audit(database, final_reaction, remaining_member):
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute(
            """SELECT group_id, state, COUNT(*) FROM pending_messages
               WHERE required_chat_features_version = 1 GROUP BY group_id, state"""
        ).fetchall()
        # Every native recipient decrypts and acknowledges the event. Each first
        # two group edits has two copies and the post-removal edit has one.
        direct = sum(count for group, _, count in rows if group is None)
        group = sum(count for group, _, count in rows if group is not None)
        require((direct, group) == (3, 5), f"Unexpected direct/group reaction fanout: {direct}/{group}.")
        require(all(state in ("delivered", "read") for _, state, _ in rows),
                "A reaction remained in the inbox after the native recipients checked it.")
        recipients = connection.execute(
            "SELECT recipient_id FROM pending_messages WHERE group_message_id = ?",
            (final_reaction,),
        ).fetchall()
        require(recipients == [(remaining_member,)], "The relay admitted an update for the removed group member.")
        return {"direct_reaction_envelopes": direct, "group_reaction_envelopes": group,
                "post_removal_reaction_recipients": len(recipients)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True, type=Path)
    parser.add_argument("--backend-python", default=sys.executable)
    parser.add_argument("--mac", default="apple@macbook-pro")
    parser.add_argument("--workspace", required=True, help="Absolute path to the built Mac workspace")
    parser.add_argument("--derived-data", required=True, help="Absolute path to the Mac simulator build")
    parser.add_argument("--ios-output", required=True, help="Existing private Mac directory for native test results")
    parser.add_argument("--ios", required=True, help="Dedicated iOS simulator UUID")
    parser.add_argument("--android", required=True, help="Dedicated Android emulator serial")
    parser.add_argument("--android-run", required=True, help="An unused three-digit Android run identifier")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--port", type=int, default=48948)
    args = parser.parse_args()
    os.umask(0o077)
    pair = NativePair(args)
    with ExitStack() as cleanup:
        # Register after mkdir succeeds, so a rerun never changes retained inputs.
        pair.run.mkdir(mode=0o700)
        cleanup.callback((pair.relay / "local-test-credentials.json").unlink, missing_ok=True)
        cleanup.callback(pair.remove_inputs)
        with ExitStack() as resources:
            pair.start(resources)
            final_reaction, remaining_member = journey(pair)
    audit = relay_audit(pair.relay / "pair.sqlite", final_reaction, remaining_member)
    write_json(pair.run / "RESULT.json", {
        "status": "passed", "revision": pair.revision, "stages": pair.stages,
        "ios_result_bundles": pair.mac_results, "android_emulator": args.android,
        "relay_audit": audit,
        "providers": {"sign_in": "synthetic loopback JWT", "push": "local APNs ticket capture"},
    })


if __name__ == "__main__":
    main()
