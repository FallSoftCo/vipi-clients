#!/usr/bin/env python3
"""Bounded, isolated CPU qualification of pinned AfriSLM GGUF weights.

Starts and stops only its own loopback llama-server. No service installation,
GPU use, model download, conversation history, or production integration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def memory(pid):
    try:
        fields = {}
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:", "VmSize:", "Threads:")):
                key, value = line.split(":", 1)
                fields[key] = value.strip()
        return fields
    except FileNotFoundError:
        return {}


def main():
    parser = argparse.ArgumentParser()
    for name in ("plan", "protocol", "server", "model", "chat-template", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), "Preserve prior captures"
    plan = json.loads(args.plan.read_text())
    protocol = json.loads(args.protocol.read_text())
    assert sha(args.protocol) == plan["source_protocol_sha256"]
    assert sha(args.model) == plan["model_sha256"]
    assert args.model.stat().st_size == plan["model_bytes"]
    rows = [r for r in protocol["messages"] if r["source"] == "en" and r["target"] == "sw"]
    if "selected_message_ids" in plan:
        selected = plan["selected_message_ids"]
        by_id = {row["id"]: row for row in rows}
        assert len(selected) == len(set(selected)) and all(item in by_id for item in selected)
        rows = [by_id[item] for item in selected]
    assert len(rows) == len({r["id"] for r in rows}) == plan.get("expected_message_count", 80)
    limits = plan["limits"]
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    command = [str(args.server), "--model", str(args.model), "--host", "127.0.0.1",
               "--port", str(port), "--threads", "2", "--threads-batch", "2",
               "--threads-http", "1", "--parallel", "1", "--ctx-size", "2048",
               "--n-gpu-layers", "0", "--device", "none", "--jinja",
               "--chat-template-file", str(args.chat_template), "--no-webui",
               "--no-warmup"]
    if plan.get("disable_server_prompt_cache", False):
        command += ["--cache-ram", "0", "--no-cache-prompt", "--no-cache-idle-slots"]
    env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    result = {"schema": "vipi-qvac-slm-local-provider-1", "production": False,
              "mobile_runtime_qualified": False, "independent_semantic_acceptance": False,
              "plan_sha256": sha(args.plan), "input_sha256": sha(args.protocol),
              "source_selection_sha256": protocol.get("source_protocol_sha256"),
              "runner_sha256": sha(__file__), "server_sha256": sha(args.server),
              "model_sha256": sha(args.model), "chat_template_sha256": sha(args.chat_template),
              "command": command, "limits": limits, "complete": False,
              "cases": [], "started_unix": time.time(), "observed_peak_rss_bytes": 0,
              "provider": "Pinned llama.cpp b12110, Q4_K_M AfriSLM0.8B, CPU only",
              "prompt_policy": "Official strict-translation system/user messages, including appended full stop and Translation cue; exact original source embedded verbatim. No prompt tuning.",
              "network_policy": "Inference uses only newly-owned loopback server and pinned local model. Host network is not disabled; no external inference endpoint configured."}
    def save():
        temporary = args.output.with_suffix(".partial")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(args.output)
    save()
    started = time.monotonic()
    finished = threading.Event()
    with args.output.with_suffix(".server.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=True)
        result["owned_pid"] = process.pid
        def monitor():
            while not finished.wait(.1):
                sample = memory(process.pid)
                rss = int(sample.get("VmRSS", "0 kB").split()[0]) * 1024
                result["observed_peak_rss_bytes"] = max(result["observed_peak_rss_bytes"], rss)
                result["memory_latest"] = sample
                reason = None
                if rss > limits["observed_rss_bytes"]:
                    reason = "observed_rss_limit"
                elif time.monotonic() - started > limits["inference_seconds"]:
                    reason = "inference_deadline"
                if reason:
                    result["termination_reason"] = reason
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    return
        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        base = f"http://127.0.0.1:{port}"
        def get(path):
            with urllib.request.urlopen(base + path, timeout=5) as response:
                return json.load(response)
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"owned server exited during preparation: {process.returncode}")
                try:
                    if get("/health").get("status") == "ok":
                        break
                except (OSError, urllib.error.HTTPError):
                    pass
                if time.monotonic() - started > 120:
                    raise TimeoutError("model preparation exceeded120seconds")
                time.sleep(.2)
            result["preparation_ms"] = (time.monotonic() - started) * 1000
            result["server_properties"] = get("/props")
            result["memory_after_preparation"] = memory(process.pid)
            save()
            for index, row in enumerate(rows):
                source = row["text"]
                messages = [{"role": "system", "content":
                    "You are a professional English to Swahili translator. "
                    "Your goal is to accurately convey the meaning and nuances of the "
                    "original English text while adhering to Swahili grammar, "
                    "vocabulary, and cultural sensitivities. Produce only the "
                    "Swahili translation, without any additional explanations "
                    "or commentary. "},
                    {"role": "user", "content":
                     f"Please translate the following English text into Swahili: {source}.\n\nTranslation:"}]
                body = {"messages": messages, "temperature": 0, "max_tokens": 256,
                        "seed": 1, "stream": False, "cache_prompt": False}
                result["in_flight"] = {"id": row["id"], "index": index, "started_unix": time.time()}
                save()
                call_started = time.monotonic()
                request = urllib.request.Request(base + "/v1/chat/completions",
                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=limits["per_request_seconds"]) as response:
                    raw = json.load(response)
                elapsed = (time.monotonic() - call_started) * 1000
                choice = raw["choices"][0]
                result["cases"].append({"id": row["id"], "source": "en", "target": "sw",
                    "corpus": row["corpus"], "length_bin": row["length_bin"], "original": source,
                    "translation": choice["message"].get("content", ""), "elapsed_ms": elapsed,
                    "status": "translated" if choice["finish_reason"] == "stop" else "generation_limit",
                    "request": body, "raw_response": raw})
                result.pop("in_flight", None)
                save()
                print(f"{index+1}/{len(rows)} {elapsed:.0f}ms", flush=True)
            result["complete"] = True
        except Exception as exc:
            result["error"] = repr(exc)
        finally:
            result["elapsed_ms"] = (time.monotonic() - started) * 1000
            finished.set()
            watcher.join(timeout=2)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            result["owned_server_exit_code"] = process.returncode
            result["finished_unix"] = time.time()
            save()
    if not result["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
