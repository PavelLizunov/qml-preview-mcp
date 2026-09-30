#!/usr/bin/env python3
"""0.3 acceptance: real layout constraints, diagnostics and dual-era stdio."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from smoke import Client, ROOT

META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "modern-fixture", "version": "1"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="qml-preview-v03-") as temporary:
        work = Path(temporary)
        evidence = options.evidence_dir.absolute() if options.evidence_dir else work / "evidence"
        evidence.mkdir()
        checks = [
            {"id": "symmetric", "kind": "symmetric", "a": "left", "b": "right", "container": "frame", "axis": "x"},
            {"kind": "align", "a": "left", "b": "right", "field": "top"},
            {"kind": "equal", "a": "left", "b": "right", "field": "width"},
            {"kind": "equal", "a": "left", "b": "right", "field": "height"},
            {"kind": "centered", "a": "frame", "container": "canvas", "axis": "x"},
            {"kind": "centered", "a": "frame", "container": "canvas", "axis": "y"},
            {"kind": "inside", "a": "left", "container": "frame"},
            {"kind": "noOverlap", "a": "left", "b": "right"},
            {"kind": "size", "a": "frame", "field": "width", "value": 440},
            {"kind": "gap", "a": "left", "b": "right", "axis": "x", "value": 240},
        ]
        def args(name="candidate.png", **changes):
            return {"qmlPath": str(ROOT / "tests" / "geometry.qml"), "outputPath": str(evidence / name),
                    "width": 480, "height": 300, "imageMode": "path", "readyProperty": "previewReady",
                    "geometryChecks": checks, "snapshot": {}, "warningsPolicy": "error", **changes}

        client = Client(work)
        try:
            for name, changes, expected in (
                ("geometry-broken.png", {"initialProperties": {"rightOffset": 12}}, "FAIL"),
                ("geometry-fixed.png", {}, "PASS"),
                ("geometry-tolerance.png", {"initialProperties": {"rightOffset": 0.5}}, "PASS"),
            ):
                result = client.call(args(name, **changes))["result"]
                metadata = result["structuredContent"]
                assert metadata["acceptance"] == expected, result
                assert result["isError"] == (expected == "FAIL")
                assert (evidence / name).is_file()
                assert len(metadata["geometryResults"]) == len(checks)
                snapshot = metadata["snapshot"]
                assert snapshot["kind"] == "QQuickItem-visual-tree" and not snapshot["truncated"]
                assert any(n["objectName"] == "reparented" for n in snapshot["nodes"])
                assert any(n.get("text") == "Geometry fixture" for n in snapshot["nodes"])
                (evidence / (name + ".json")).write_text(json.dumps(metadata, indent=2) + "\n")
            print("PASS: every rule family, explicit symmetry failure/fix, 1-unit tolerance, retained FAIL PNG and visual snapshot")

            metadata = client.call(args("truncated.png", snapshot={"maxItems": 2, "maxDepth": 1}))["result"]["structuredContent"]
            assert metadata["snapshot"]["truncated"] and len(metadata["snapshot"]["nodes"]) <= 2
            result = client.call(args("missing.png", geometryChecks=[{"kind": "size", "a": "absent", "field": "width", "value": 2}]))["result"]
            assert result["isError"] and result["structuredContent"]["geometryResults"][0]["status"] == "FAIL"
            result = client.call(args("measure-reparented.png", measureObjects=["reparented"], geometryChecks=[]))["result"]
            assert result["structuredContent"]["measurements"]["reparented"]["x"] == 40
            for malformed in ([{"kind": "unknown"}], [{"kind": []}], [{"kind": "size", "a": "left", "field": "width", "value": -1}],
                              [{"kind": "inside", "a": "left", "container": "frame", "tolerance": True}],
                              [{"kind": "inside", "a": "left", "container": "frame", "extra": 1}]):
                assert client.call(args(geometryChecks=malformed))["error"]["code"] == -32602
            assert client.call(args(snapshot={"maxItems": 257}))["error"]["code"] == -32602
            print("PASS: missing assertion targets, visual-only reparenting, snapshot truncation and option bounds")

            warning = work / "warning.qml"
            warning.write_text('import QtQuick\nRectangle { Component.onCompleted: console.warn("strict fixture warning") }')
            for policy in ("report", "error"):
                result = client.call(args("warning-" + policy + ".png", qmlPath=str(warning), geometryChecks=[],
                                          readyProperty="visible", warningsPolicy=policy))["result"]
                assert result["isError"] == (policy == "error"), result
                assert any(r["level"] == "warning" and "strict fixture warning" in r["message"] for r in result["structuredContent"]["diagnosticRecords"])
                assert (evidence / ("warning-" + policy + ".png")).is_file()
            print("PASS: typed warning diagnostics, report/error policy and retained diagnostic image")

            # Modern inline requests work alongside legacy requests, without discovery/initialize state.
            result = client.request("server/discover", {"_meta": META})["result"]
            assert result["resultType"] == "complete" and result["ttlMs"] == 0 and result["cacheScope"] == "private"
            assert "2026-07-28" in result["supportedVersions"]
            assert client.request("tools/list", {"_meta": META})["result"]["resultType"] == "complete"
            assert client.request("tools/list")["result"].get("resultType") is None
            response = client.request("tools/call", {"_meta": META, "name": "render_qml", "arguments": args("modern.png")})
            assert response["result"]["resultType"] == "complete" and not response["result"]["isError"]
            for params, code in (({"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}, -32602),
                                 ({"_meta": {"io.modelcontextprotocol/clientCapabilities": {}}}, -32602),
                                 ({"_meta": {**META, "io.modelcontextprotocol/protocolVersion": "2099-01-01"}}, -32022)):
                assert client.request("tools/list", params)["error"]["code"] == code
            result = client.request("tools/call", {"_meta": META, "name": "render_qml", "arguments": {"width": 0}})["result"]
            assert result["isError"] and result["resultType"] == "complete"
            assert client.request("ping", {"_meta": META})["error"]["code"] == -32601
            assert client.request("ping")["result"] == {}
            assert client.request("tools/call", {"_meta": META, "name": "render_qml", "arguments": []})["error"]["code"] == -32602
            assert client.request("tools/call", {"_meta": META, "name": "healthcheck", "unexpected": 1})["error"]["code"] == -32602
            print("PASS: modern discovery/inline calls, per-request version, cache fields, errors and interleaved legacy context")

            client.process.stdin.write('{"jsonrpc":"2.0","id":99,"method":"ping"}\n'.encode("utf-16"))
            client.process.stdin.flush()
            assert client.read()["error"]["code"] == -32700
            # The UTF-16 newline leaves one trailing NUL; terminate and reject it
            # separately, then prove the UTF-8 stream remains usable.
            client.process.stdin.write(b"\n")
            client.process.stdin.flush()
            assert client.read()["error"]["code"] == -32700
            assert client.request("ping")["result"] == {}
            print("PASS: non-UTF8 input rejected with recoverable framing")

            blocked = work / "blocked.qml"
            blocked.write_text("import QtQuick\nItem { Component.onCompleted: { while (true) {} } }")
            ids = list(range(1000, 1008))
            for request_id in ids:
                client.write({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
                    "name": "render_qml", "arguments": args("queued.png", qmlPath=str(blocked), timeoutMs=10000)}})
            assert client.request("tools/call", {"name": "healthcheck"})["error"]["code"] == -32602
            for request_id in ids:
                client.write({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": request_id}})
            # Queue cleanup follows the single worker; healthcheck then verifies recovery.
            time.sleep(0.3)
            assert not client.request("tools/call", {"name": "healthcheck"})["result"]["isError"]
            assert not (evidence / "queued.png").exists()
            print("PASS: bounded queue admission, queued/active cancellation and recovery without candidate output")
        finally:
            client.close()

        # No legacy handshake: modern first request is independently served.
        process = subprocess.Popen(["python3", "-B", str(ROOT / "mcp-qml-preview.py")], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}}
        stdout, stderr = process.communicate(json.dumps(request).encode() + b"\n", timeout=5)
        assert process.returncode == 0 and not stderr and json.loads(stdout)["result"]["resultType"] == "complete"
        print("PASS: modern first request without handshake")

        spec = importlib.util.spec_from_file_location("preview", ROOT / "mcp-qml-preview.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        boxes = {"a": {"x": 10, "y": 10, "width": 20, "height": 20, "visible": True},
                 "b": {"x": 70, "y": 10, "width": 20, "height": 20, "visible": True},
                 "c": {"x": 0, "y": 0, "width": 100, "height": 100, "visible": True}}
        rules = [
            {"kind": "align", "a": "a", "b": "b", "field": "left"},
            {"kind": "equal", "a": "a", "b": "c", "field": "width"},
            {"kind": "centered", "a": "a", "container": "c", "axis": "x"},
            {"kind": "inside", "a": "c", "container": "a"},
            {"kind": "noOverlap", "a": "a", "b": "a"},
            {"kind": "size", "a": "a", "field": "height", "value": 25},
            {"kind": "gap", "a": "a", "b": "b", "axis": "x", "value": 20},
        ]
        assert all(r["status"] == "FAIL" for r in module.geometry_results(rules, boxes))
        assert module.geometry_results([{"kind": "symmetric", "a": "a", "b": "b", "container": "c", "axis": "x"}], boxes)[0]["status"] == "PASS"
        boxes["b"]["height"] = 23
        assert module.geometry_results([{"kind": "symmetric", "a": "a", "b": "b", "container": "c", "axis": "x"}], boxes)[0]["status"] == "FAIL"
        print("PASS: negative cases for every geometry family and mirrored-pair size invariants")
        fake = work / "qml-render"
        fake.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"rendererVersion":"0.2.0","backend":"software","platform":"offscreen"}))\n')
        fake.chmod(0o700)
        module.RENDERER = fake
        try:
            module.healthcheck(__import__("threading").Event())
            raise AssertionError("Stale renderer accepted")
        except module.ToolFailure as exc:
            assert exc.code == "VERSION_MISMATCH"
        print("PASS: renderer/wrapper version mismatch refuses stale binary")
        print("Evidence:", evidence)


if __name__ == "__main__":
    main()
