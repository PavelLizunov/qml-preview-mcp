#!/usr/bin/env python3
"""Deterministic admission/IPC tests; optional actual consumer pixel check."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time

from smoke import Client, ROOT, png
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("capture_mcp", ROOT / "mcp-qml-preview.py")
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)
bridge = api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path)
    parser.add_argument("--imports", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--negative-state", choices=["hidden", "disabled"])
    parser.add_argument("--dpr", type=int, choices=[1, 2], default=1)
    parser.add_argument("--native-negatives", action="store_true")
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="capture-tests-") as tmp:
        work = Path(tmp)
        client = Client(work)
        args = {"pluginId": bridge.CAPTURE_PLUGIN_ID, "consent": bridge.CAPTURE_REQUEST_CONSENT, "outputPath": str(work / "capture.png")}
        def call(value):
            return client.request("tools/call", {"name": "capture_plugin_page", "arguments": value})
        try:
            catalog = client.request("tools/list")["result"]["tools"]
            tools = {t["name"]: t for t in catalog}
            assert set(tools) == {"healthcheck", "render_qml", "capture_plugin_page"}
            assert tools["capture_plugin_page"]["inputSchema"]["additionalProperties"] is False
            assert "fixture" in tools["render_qml"]["description"]
            capture = tools["capture_plugin_page"]
            assert capture["inputSchema"]["properties"]["consent"]["enum"] == [bridge.CAPTURE_REQUEST_CONSENT, bridge.CAPTURE_CONSENT]
            assert "no second confirmation" in capture["description"]
            assert "may inspect it when the user authorizes image review" in capture["description"]
            assert "never attach or send account images" not in capture["description"]
            assert "user-authorized image inspection" in capture["inputSchema"]["properties"]["outputPath"]["description"]
            assert bridge.validate_capture(args, api.InvalidParams)["consent"] == bridge.CAPTURE_REQUEST_CONSENT
            assert bridge.validate_capture({**args, "consent": bridge.CAPTURE_CONSENT}, api.InvalidParams)["consent"] == bridge.CAPTURE_CONSENT
            # Source implementation alone is not permission. Missing/false/generic
            # assertions must fail before any endpoint or browser connection.
            missing = {k: v for k, v in args.items() if k != "consent"}
            assert call(missing)["error"]["code"] == -32602
            assert call({**args, "consent": "Implement the capture bridge"})["error"]["code"] == -32602
            for changes in ({"consent": "yes"}, {"consent": None}, {"pluginId": "other"}, {"target": "auxiliary"},
                            {"script": "document.cookie"}, {"command": "echo"}, {"url": "https://chatgpt.com"},
                            {"outputPath": "relative.png"}, {"outputPath": str(work / "../bad.png")},
                            {"timeoutMs": True}, {"timeoutMs": 5001}, {"imageMode": "image"}, {"consent": False}):
                assert call({**args, **changes})["error"]["code"] == -32602
            (work / "original.png").write_text("untouched")
            result = call({**args, "outputPath": str(work / "original.png")})["result"]
            assert result["structuredContent"]["error"]["code"] == "OUTPUT_EXISTS"
            assert (work / "original.png").read_text() == "untouched"
            (work / "alias").symlink_to(work, target_is_directory=True)
            assert call({**args, "outputPath": str(work / "alias/capture.png")})["result"]["isError"]
            git = work / "git"; git.mkdir(); (git / ".git").write_text("gitdir: /unused")
            result = call({**args, "outputPath": str(git / "account.png")})["result"]
            assert "outside Git" in result["structuredContent"]["error"]["message"]
            modern = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
            denied = client.request("tools/call", {"_meta": modern, "name": "capture_plugin_page", "arguments": {**args, "consent": "no"}})
            assert denied["result"]["isError"] and denied["result"]["resultType"] == "complete"
            assert not (work / "capture.png").exists()
        finally:
            client.close()
        print("PASS: tool discovery, user-scoped image review, closed consent/target/schema, collision, symlink, Git and path-only transport")

        # Isolated fake peer tests validate failure framing and bounds only.
        # This is not evidence of browser pixel capture.
        original = bridge.endpoint
        fake = work / "private"; fake.mkdir(mode=0o700)
        bridge.endpoint = lambda: fake / "capture.sock"
        try:
            try:
                bridge.capture_page({**args, "timeoutMs": 100}, threading.Event(), threading.Lock(), api)
                raise AssertionError("Missing isolated bridge was admitted")
            except api.ToolFailure as exc:
                assert exc.code == "BRIDGE_UNAVAILABLE"
            for mode in ("hidden", "oversize", "incomplete", "timeout", "cancel", "unsafe"):
                server = socket.socket(socket.AF_UNIX); server.bind(str(bridge.endpoint())); server.listen(1)
                os.chmod(bridge.endpoint(), 0o644 if mode == "unsafe" else 0o600)
                stopped = threading.Event()
                def serve():
                    server.settimeout(0.5)
                    try:
                        peer, _ = server.accept()
                        with peer:
                            peer.recv(1024)
                            if mode == "hidden":
                                payload = b'{"error":{"code":"HIDDEN_UNSUPPORTED"}}'
                                peer.sendall(struct.pack(">II", len(payload), 0) + payload)
                            elif mode == "oversize": peer.sendall(struct.pack(">II", 65537, 0))
                            elif mode == "incomplete": peer.sendall(b"xx")
                            else: stopped.wait(0.4)
                    except (socket.timeout, BrokenPipeError): pass
                worker = threading.Thread(target=serve); worker.start()
                cancelled = threading.Event()
                if mode == "cancel": cancelled.set()
                start = time.monotonic()
                try:
                    bridge.capture_page({**args, "timeoutMs": 100}, cancelled, threading.Lock(), api)
                    raise AssertionError("Negative capture succeeded")
                except (RuntimeError, ValueError, OSError): pass
                finally:
                    stopped.set(); worker.join(timeout=1); server.close(); bridge.endpoint().unlink()
                assert not worker.is_alive() and time.monotonic() - start < 1.5
                assert not (work / "capture.png").exists()
                assert not list(work.glob(".qml-preview-*"))
        finally:
            bridge.endpoint = original
        print("PASS: private peer mode, hidden error, bounded frames, incomplete response, timeout, cancellation and cleanup")

        if options.consumer:
            assert options.imports and options.evidence_dir
            evidence = options.evidence_dir.absolute(); evidence.mkdir(mode=0o700)
            assert not bridge.endpoint().exists(), "Do not replace any existing bridge"
            render_client = Client(work); capture_client = Client(work)
            try:
                render_client.request_id += 1
                render_id = render_client.request_id
                render_client.write({"jsonrpc": "2.0", "id": render_id, "method": "tools/call", "params": {
                    "name": "render_qml", "arguments": {"qmlPath": str(options.consumer.absolute()),
                        "outputPath": str(evidence / "wrapper.png"), "width": 480, "height": 320, "dpr": options.dpr,
                        "importPaths": [str(options.imports.absolute())], "readyProperty": "previewReady",
                        "timeoutMs": 9000, "imageMode": "path", "locale": "en_US",
                        "initialProperties": {"hideForCapture": options.negative_state == "hidden",
                                              "enableCapture": options.negative_state != "disabled"},
                        "dependencyPaths": [str(options.consumer.parent.parent / "native" / n)
                                            for n in ("Browser.qml", "Capture.qml", "Service.qml", "Content.qml", "Theme.js")],
                        "warningsPolicy": "report"}}})
                # Wait for endpoint creation, not repeated capture requests. One
                # capture only after a bounded paint allowance, not settled proof.
                deadline = time.monotonic() + 4
                if options.negative_state != "disabled":
                    while not bridge.endpoint().exists() and time.monotonic() < deadline: time.sleep(0.02)
                    assert bridge.endpoint().exists(), "Native bridge did not load"
                time.sleep(0.7)
                if options.negative_state != "disabled":
                    # Verify the bridge belongs to this test's renderer before
                    # any consent assertion; never talk to a production bridge.
                    with socket.socket(socket.AF_UNIX) as probe:
                        probe.settimeout(1)
                        probe.connect(str(bridge.endpoint()))
                        peer_pid, uid, _ = struct.unpack("3i", probe.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        assert uid == os.getuid()
                        info = Path(f"/proc/{peer_pid}/status").read_text()
                        parent_pid = int(next(line.split()[1] for line in info.splitlines() if line.startswith("PPid:")))
                        assert parent_pid == render_client.process.pid, "Never capture from an unrelated owner"
                    time.sleep(0.1)  # Allow disconnected probe cleanup, no capture retries.
                if options.native_negatives:
                    for payload, code in (
                        (b'{}\n', 'ADMISSION_DENIED'),
                        (b'{broken\n', 'ADMISSION_DENIED'),
                        (b'x' * 1025 + b'\n', 'BAD_REQUEST'),
                        (b'{"operation":"capture","pluginId":"other","consent":"local-account-image"}\n', 'ADMISSION_DENIED'),
                        (b'{"operation":"capture","pluginId":"slovn.chatgpt-lite","consent":"no"}\n', 'ADMISSION_DENIED'),
                    ):
                        with socket.socket(socket.AF_UNIX) as probe:
                            probe.settimeout(1)
                            probe.connect(str(bridge.endpoint()))
                            assert struct.unpack("3i", probe.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0] == peer_pid
                            probe.sendall(payload)
                            deadline = time.monotonic() + 1
                            size, image_size = struct.unpack(">II", bridge.receive(probe, 8, deadline, threading.Event()))
                            rejected = json.loads(bridge.receive(probe, size, deadline, threading.Event()))
                            assert image_size == 0 and rejected["error"]["code"] == code, rejected
                        time.sleep(0.05)
                    print("PASS: actual native bridge refuses malformed/oversize/wrong-plugin/no-consent requests without PNG")
                result = capture_client.request("tools/call", {"name": "capture_plugin_page", "arguments": {
                    **args, "outputPath": str(evidence / "browser.png")}})["result"]
                (evidence / "browser.json").write_text(json.dumps(result, indent=2) + "\n")
                if options.negative_state:
                    expected = "HIDDEN_UNSUPPORTED" if options.negative_state == "hidden" else "BRIDGE_UNAVAILABLE"
                    assert result["isError"] and result["structuredContent"]["error"]["code"] == expected, result
                    assert not (evidence / "browser.png").exists()
                else:
                    assert not result["isError"], result
                    w, h, pixel = png(evidence / "browser.png")
                    scale = options.dpr
                    assert (w, h) == (480 * scale, 320 * scale)
                    assert pixel(450 * scale, 60 * scale) == (233, 30, 99) and pixel(450 * scale, 160 * scale) == (21, 101, 192)
                    assert pixel(450 * scale, 300 * scale) == (255, 255, 255)
                assert all(c["type"] == "text" for c in result["content"])
                rendered = render_client.read()
                (evidence / "wrapper.json").write_text(json.dumps(rendered, indent=2) + "\n")
                assert not rendered["result"]["isError"], rendered
                if not options.negative_state:
                    assert result["structuredContent"]["pageKind"] == "inert-local-fixture"
                    assert (evidence / "browser.png").stat().st_mode & 0o777 == 0o600
                assert not bridge.endpoint().exists(), "Native endpoint survived renderer teardown"
                print("PASS: actual consumer " + (options.negative_state + " refusal and teardown" if options.negative_state else "Chromium colors/CRC -> native bridge -> MCP path-only PNG; inspection still required"))
            finally:
                # A failed assertion must cancel the renderer before closing the
                # stdio server, otherwise its longer fixture deadline can outlive
                # Client.close and leave a killed-server child/stale socket.
                if 'render_id' in locals() and render_client.process.poll() is None:
                    render_client.write({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": render_id}})
                render_client.close(); capture_client.close()


if __name__ == "__main__":
    main()
