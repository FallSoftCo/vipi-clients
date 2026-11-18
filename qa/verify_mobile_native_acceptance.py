#!/usr/bin/env python3
"""Verify retained native acceptance evidence; never launch tests or devices.

Usage:
    python3 qa/verify_mobile_native_acceptance.py --self-test
    python3 qa/verify_mobile_native_acceptance.py /path/to/reviewed-manifest.json

mobile-native-acceptance-example.json is documentation with PLACEHOLDER paths
and hashes; it intentionally cannot pass. Copy it, review the exact required
test identities before dispatch, and fill in one unique run identity, frozen
source revision, existing native log/receipt paths and their SHA256 pins.
Expected selection must not be derived from the observed test result.

Supported checks: paired Android instrumentation identities; XCTest completed
case identities; receipt field equality (including strict true/false types);
and the authored preview matrix's exact directed pairs/native gesture fields.
Every manifest requires at least one native Android/XCTest log check. Pin source
and run identity using receipt equals fields plus hashed source evidence. Pin
restoration and additional native screenshots/geometry as reviewed artifacts;
the verifier hashes them but does not interpret pixels or spoken output.

This program reads only the files explicitly named in the local manifest. It
does not use network, credentials, SDKs, account sessions, private-log uploads,
or app/device control, and prints only check outcomes/counts and failure labels.
Run it only against locally authorized evidence. A passing result verifies the
selected retained evidence, not a new native execution, complete UX, linguistic
accuracy, acoustic quality, or release readiness. Missing environments and
physical-only tests must remain explicit exclusions; never replace them with
mock passes. Unknown, missing, duplicate or skipped required cases fail closed.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def same_cases(observed, expected):
    require(isinstance(expected, list) and bool(expected) and
            all(isinstance(case, str) and bool(case.strip()) for case in expected) and
            len(set(expected)) == len(expected), "invalid selection")
    require(len(observed) == len(expected), "missing/extra/repeated test result")
    require({case for case, _ in observed} == set(expected), "test identity differs")
    require(all(status == "passed" for _, status in observed), "failed/skipped/unknown test")


def android_cases(text):
    terminals = re.findall(r"^OK \((\d+) tests?\)\s*$", text, re.M)
    require(len(terminals) == 1, "exactly one Android terminal OK required")
    require(not re.search(r"FAILURES!!!|^INSTRUMENTATION_(?:FAILED|ABORTED):|"
                          r"^INSTRUMENTATION_RESULT: shortMsg=|^INSTRUMENTATION_STATUS: Error=|"
                          r"^Error:|^INSTRUMENTATION_CODE: (?!-1\s*$)", text, re.M),
            "contradictory Android failure/abort")
    fields, observed, active, seen, terminal_seen = {}, [], None, set(), False
    declared_counts = set()
    for line in text.splitlines():
        if re.fullmatch(r"OK \(\d+ tests?\)\s*", line):
            require(active is None and not fields, "terminal OK before Android case completed")
            terminal_seen = True
        if line.startswith("INSTRUMENTATION_STATUS: "):
            require(not terminal_seen, "Android status after terminal OK")
            key, sep, value = line.removeprefix("INSTRUMENTATION_STATUS: ").partition("=")
            if sep:
                fields[key] = value
        elif line.startswith("INSTRUMENTATION_STATUS_CODE:"):
            require(not terminal_seen, "Android completion after terminal OK")
            code = int(line.partition(":")[2])
            require(code in (0, 1), f"instrumentation skipped/failed/unknown status {code}")
            require("class" in fields and "test" in fields, "missing native test identity")
            case = fields["class"] + "#" + fields["test"]
            if "numtests" in fields:
                declared_counts.add(int(fields["numtests"]))
            if code == 1:
                require(active is None and case not in seen, "unmatched/repeated Android start")
                active = case
            else:
                require(active == case, "Android end does not match active start")
                observed.append((case, "passed"))
                seen.add(case)
                active = None
            fields = {}
    require(active is None and not fields, "dangling Android start/status")
    require(int(terminals[0]) == len(observed) > 0, "Android terminal count differs from paired completions")
    require(not declared_counts or declared_counts == {len(observed)}, "Android declared count differs")
    return observed


def ios_cases(text):
    success = r"\*\* TEST(?: EXECUTE)? SUCCEEDED \*\*\s*"
    require(len(re.findall(r"^" + success + r"$", text, re.M)) == 1,
            "exactly one XCTest terminal success required")
    require(not re.search(r"^\*\* TEST(?: EXECUTE)? FAILED \*\*|^Test Suite '.+' failed at", text, re.M),
            "contradictory XCTest failure")
    active, completed, observed, terminal_seen = set(), set(), [], False
    for line in text.splitlines():
        if re.fullmatch(success, line):
            require(not active, "XCTest success with dangling starts")
            terminal_seen = True
        event = re.search(r"Test Case '-\[([^ ]+) ([^\]]+)\]' (started|passed|failed|skipped|expected failure)", line)
        if not event:
            continue
        require(not terminal_seen, "XCTest event after terminal success")
        module, method, state = event.groups()
        case = module + "/" + method
        if state == "started":
            require(case not in active and case not in completed, "duplicate XCTest start")
            active.add(case)
        else:
            require(case in active and case not in completed, "XCTest completion without matching start")
            active.remove(case); completed.add(case); observed.append((case, state))
    require(not active and bool(observed), "dangling/empty XCTest execution")
    return observed


def preview_matrix(value, languages):
    require(len(languages) > 1 and len(languages) == len(set(languages)), "invalid language selection")
    expected = set(itertools.permutations(languages, 2))
    rows = value["directions"]
    require(value.get("complete") is True, "matrix incomplete")
    require(len(rows) == len(expected), "matrix row count")
    require({(r["source"], r["target"]) for r in rows} == expected, "matrix missing/duplicate direction")
    require(value.get("expected_directions") == len(expected), "matrix expected count")
    require(value.get("passed_directions") == len(expected) and value.get("failed_directions") == 0,
            "matrix aggregate mismatch")
    for row in rows:
        require(row.get("status") == "passed", "matrix skipped/failed row")
        require(all(row.get(k) is True for k in ("native_playing_observed", "same_word_stop", "no_rebound")),
                "matrix native start/stop evidence missing")
        require(row.get("accepted_language") == row["target"] and bool(row.get("accepted_script")),
                "matrix audio language/script mismatch")
        require(row["accepted_script"] == row.get("target_script"), "matrix spoke a different word")
        require(bool(row.get("displayed_word")) and bool(row.get("word_bounds")), "matrix visible-word proof missing")


def verify(manifest):
    require(type(manifest.get("schema")) is int and manifest["schema"] == 1, "unsupported selection schema")
    require(isinstance(manifest.get("run_id"), str) and bool(manifest["run_id"].strip()), "missing run identity")
    require(isinstance(manifest.get("selectionAuthority"), str) and bool(manifest["selectionAuthority"].strip()),
            "missing independently reviewed selection authority")
    require(isinstance(manifest.get("artifacts"), list) and bool(manifest["artifacts"]), "empty artifacts")
    require(isinstance(manifest.get("checks"), list) and bool(manifest["checks"]), "empty selection")
    require(any(c.get("type") in ("android", "ios") for c in manifest["checks"]), "missing native execution evidence check")
    require(isinstance(manifest.get("limits"), list) and bool(manifest["limits"]), "missing evidence boundaries")
    pinned = {}
    for item in manifest["artifacts"]:
        require(isinstance(item.get("id"), str) and bool(item["id"].strip()), "missing artifact identity")
        require(item["id"] not in pinned, "duplicate artifact identity")
        require(isinstance(item.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", item["sha256"]), "invalid artifact SHA256")
        path = Path(item["path"])
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == item["sha256"], "artifact drift: " + str(path))
        pinned[item["id"]] = data
    reports, check_ids = [], set()
    for check in manifest["checks"]:
        require(isinstance(check.get("id"), str) and bool(check["id"].strip()), "missing check identity")
        require(check["id"] not in check_ids, "duplicate check identity")
        check_ids.add(check["id"])
        require(check.get("artifact") in pinned, "unbound check artifact")
        data = pinned[check["artifact"]]
        kind = check["type"]
        if kind in ("android", "ios"):
            parser = android_cases if kind == "android" else ios_cases
            observed = parser(data.decode())
            same_cases(observed, check["expected_cases"])
            reports.append({"check": check["id"], "passed_cases": len(observed)})
        elif kind == "preview_matrix":
            preview_matrix(json.loads(data), check["languages"])
            reports.append({"check": check["id"], "passed_directions": len(check["languages"]) * (len(check["languages"]) - 1)})
        elif kind == "receipt":
            require(isinstance(check.get("equals"), dict) and bool(check["equals"]), "empty receipt assertions")
            value = json.loads(data)
            for key, expected in check["equals"].items():
                require(key in value and type(value[key]) is type(expected) and value[key] == expected,
                        "receipt missing/mismatched field: " + key)
            reports.append({"check": check["id"], "verified": True})
        else:
            raise ValueError("unsupported check type: " + kind)
    return {"complete": True, "status": "retained_evidence_verified", "checks": reports,
            "new_native_execution": False, "release_ready": False,
            "limits": manifest["limits"]}


def self_test():
    negatives = [([], ["A"]), ([("B", "passed")], ["A"]),
                 ([("A", "skipped")], ["A"]), ([("A", "failed")], ["A"]),
                 ([("A", "passed"), ("A", "passed")], ["A"]), ([], []),
                 ([("A", "passed")], "A"), ([("A", "passed")], [""])]
    for observed, expected in negatives:
        try:
            same_cases(observed, expected)
        except ValueError:
            continue
        raise AssertionError("negative case incorrectly passed")
    for code in (-1, -2, -3, -4):
        try:
            android_cases("INSTRUMENTATION_STATUS_CODE: " + str(code) + "\nOK (1 test)")
        except ValueError:
            continue
        raise AssertionError("nonpass instrumentation incorrectly passed")
    same_cases([("A", "passed")], ["A"])
    fixture = {"complete": True, "expected_directions": 2, "passed_directions": 2,
               "failed_directions": 0, "directions": [
                   {"source": s, "target": t, "status": "passed", "native_playing_observed": True,
                    "same_word_stop": True, "no_rebound": True, "accepted_language": t,
                    "accepted_script": "word", "target_script": "word", "displayed_word": "word",
                    "word_bounds": "[1,1][10,10]"} for s, t in [("en", "es"), ("es", "en")]]}
    preview_matrix(fixture, ["en", "es"])
    for mutation in ("duplicate", "incomplete", "skipped", "wrong_word", "no_native_start"):
        bad = json.loads(json.dumps(fixture))
        if mutation == "duplicate": bad["directions"][1] = bad["directions"][0]
        if mutation == "incomplete": bad["complete"] = False
        if mutation == "skipped": bad["directions"][0]["status"] = "skipped"
        if mutation == "wrong_word": bad["directions"][0]["accepted_script"] = "wrong"
        if mutation == "no_native_start": bad["directions"][0]["native_playing_observed"] = False
        try:
            preview_matrix(bad, ["en", "es"])
        except ValueError:
            continue
        raise AssertionError("negative matrix case incorrectly passed: " + mutation)
    def block(case, code):
        return "INSTRUMENTATION_STATUS: class=Example\nINSTRUMENTATION_STATUS: test=" + case + "\nINSTRUMENTATION_STATUS_CODE: " + str(code) + "\n"
    paired = block("A", 1) + block("A", 0)
    valid = paired + "OK (1 test)\n"
    same_cases(android_cases(valid), ["Example#A"])
    negative_logs = {
        "dangling_B_after_passed_A": paired + block("B", 1) + "OK (1 test)\n",
        "mismatched_start_end": block("A", 1) + block("B", 0) + "OK (1 test)\n",
        "end_without_start": block("A", 0) + "OK (1 test)\n",
        "overlapping_starts": block("A", 1) + block("B", 1) + block("A", 0) + "OK (1 test)\n",
        "duplicate_terminal_OK": valid + "OK (1 test)\n",
        "terminal_count_mismatch": paired + "OK (2 tests)\n",
        "success_followed_by_FAILURES": valid + "FAILURES!!!\n",
        "success_followed_by_instrumentation_failure": valid + "INSTRUMENTATION_FAILED: process crashed\n",
        "success_followed_by_abort": valid + "INSTRUMENTATION_ABORTED: stopped\n",
        "success_followed_by_crash_shortMsg": valid + "INSTRUMENTATION_RESULT: shortMsg=Process crashed.\n",
        "terminal_OK_before_completion": block("A", 1) + "OK (1 test)\n" + block("A", 0),
    }
    for name, text in negative_logs.items():
        try:
            android_cases(text)
        except ValueError:
            continue
        raise AssertionError("false-green native log accepted: " + name)
    def ios_event(case, state):
        return "Test Case '-[ExampleUITests.JourneyTests " + case + "]' " + state + ".\n"
    ios_pair = ios_event("testA", "started") + ios_event("testA", "passed")
    ios_terminal = "** TEST EXECUTE SUCCEEDED **\n"
    same_cases(ios_cases(ios_pair + ios_terminal), ["ExampleUITests.JourneyTests/testA"])
    parallel = (ios_event("testA", "started") + ios_event("testB", "started") +
                ios_event("testB", "passed") + ios_event("testA", "passed") + ios_terminal)
    same_cases(ios_cases(parallel), ["ExampleUITests.JourneyTests/testA", "ExampleUITests.JourneyTests/testB"])
    ios_negatives = {
        "passed_A_dangling_B_success": ios_pair + ios_event("testB", "started") + ios_terminal,
        "success_and_failure_markers": ios_pair + ios_terminal + "** TEST EXECUTE FAILED **\n",
        "mismatched_started_completed_case": ios_event("testA", "started") + ios_event("testB", "passed") + ios_terminal,
        "completion_without_start": ios_event("testA", "passed") + ios_terminal,
        "duplicate_completion": ios_pair + ios_event("testA", "passed") + ios_terminal,
        "duplicate_success_marker": ios_pair + ios_terminal + ios_terminal,
        "case_after_terminal_success": ios_pair + ios_terminal + ios_event("testB", "started"),
    }
    for name, text in ios_negatives.items():
        try:
            ios_cases(text)
        except ValueError:
            continue
        raise AssertionError("false-green XCTest log accepted: " + name)
    import tempfile
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
        log = Path(temporary) / "native.log"
        log.write_text(valid)
        selected = {"schema": 1, "run_id": "self-test-run", "selectionAuthority": "independent self-test selection",
                    "limits": ["synthetic parser input only"], "artifacts": [
                        {"id": "native", "path": str(log), "sha256": hashlib.sha256(log.read_bytes()).hexdigest()}],
                    "checks": [{"id": "selected", "type": "android", "artifact": "native", "expected_cases": ["Example#A"]}]}
        verify(selected)
        mutations = {
            "empty_checks": lambda x: x.update(checks=[]),
            "empty_artifacts": lambda x: x.update(artifacts=[]),
            "duplicate_check_ID": lambda x: x["checks"].append(dict(x["checks"][0])),
            "unbound_artifact_reference": lambda x: x["checks"][0].update(artifact="absent"),
            "unsupported_selection_schema": lambda x: x.update(schema=99),
            "missing_independent_selection_authority": lambda x: x.pop("selectionAuthority"),
            "missing_run_identity": lambda x: x.pop("run_id"),
            "duplicate_artifact_identity": lambda x: x["artifacts"].append(dict(x["artifacts"][0])),
            "artifact_content_drift": lambda x: x["artifacts"][0].update(sha256="0" * 64),
            "receipt_or_matrix_only_without_native_log": lambda x: x["checks"][0].update(type="receipt", equals={"complete": True}),
        }
        for name, mutate in mutations.items():
            bad = json.loads(json.dumps(selected)); mutate(bad)
            try:
                verify(bad)
            except ValueError:
                continue
            raise AssertionError("false-green manifest accepted: " + name)
    return {"self_test": "passed", "native_protocol_negative_cases": list(negative_logs),
            "xctest_protocol_negative_cases": list(ios_negatives), "distinct_parallel_xctest_cases": "passed",
            "manifest_negative_cases": list(mutations), "base_selection_and_matrix_negatives": 17,
            "new_native_execution": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else verify(json.loads(Path(args.manifest).read_text()))
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(json.dumps({"complete": False, "status": "rejected", "error": str(error)}))
        raise SystemExit(1)
