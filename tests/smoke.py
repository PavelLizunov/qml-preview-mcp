#!/usr/bin/env python3
"""Build first; run this dependency-free acceptance check from any directory."""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixture.qml"
IMPORTS = ROOT / "tests" / "imports"


class Client:
    def __init__(self, cwd, protocol="2025-06-18", wrapper=None):
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(wrapper or ROOT / "mcp-qml-preview.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd,
            # Poison import/scale variables to prove explicit inputs win.
            env={**os.environ, "QML_IMPORT_PATH": str(cwd / "stale-imports"),
                 "QML2_IMPORT_PATH": str(cwd / "stale-imports"),
                 "QT_SCALE_FACTOR": "3", "QT_SCREEN_SCALE_FACTORS": "3"},
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.request_id = 0
        self.buffer = bytearray()
        result = self.request("initialize", {
            "protocolVersion": protocol, "capabilities": {},
            "clientInfo": {"name": "qml-preview-smoke", "version": "1"},
        })
        assert result["result"]["protocolVersion"] == protocol
        self.write({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def write(self, message):
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()

    def read(self):
        while b"\n" not in self.buffer:
            assert self.selector.select(timeout=15), "MCP response timed out"
            data = os.read(self.process.stdout.fileno(), 65536)
            assert data, "MCP closed stdout unexpectedly"
            self.buffer.extend(data)
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        return json.loads(line)

    def request(self, method, params=None):
        self.request_id += 1
        message = {"jsonrpc": "2.0", "id": self.request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.write(message)
        response = self.read()
        assert response["jsonrpc"] == "2.0" and response["id"] == self.request_id
        return response

    def call(self, args):
        return self.request("tools/call", {"name": "render_qml", "arguments": args})

    def close(self):
        self.process.stdin.close()
        try:
            assert self.process.wait(timeout=5) == 0
            assert not self.process.stderr.read(), "Server wrote unexpected stderr"
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait()
            self.selector.close()
            self.process.stdout.close()
            self.process.stderr.close()


def png(path):
    """Check CRCs, decompress pixels and sample the fixture's RGB colors."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed, ended = 8, bytearray(), False
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        checksum = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        assert zlib.crc32(kind + payload) == checksum, "PNG CRC mismatch"
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            assert depth == 8 and color in (2, 6) and (compression, filtering, interlace) == (0, 0, 0)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            ended = True
        offset += length + 12
    assert ended and offset == len(data)
    raw = zlib.decompress(compressed)
    channels = 4 if color == 6 else 3
    stride = width * channels
    assert len(raw) == (stride + 1) * height
    rows, previous = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        method = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        assert method in range(5)
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = previous[x]
            upper_left = previous[x - channels] if x >= channels else 0
            if method == 1:
                predictor = left
            elif method == 2:
                predictor = up
            elif method == 3:
                predictor = (left + up) // 2
            elif method == 4:
                p = left + up - upper_left
                candidates = (left, up, upper_left)
                predictor = min(candidates, key=lambda c: abs(p - c))
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        rows.append(row)
        previous = row

    def pixel(x, y):
        return tuple(rows[y][x * channels:x * channels + 3])

    return width, height, pixel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path,
                        help="New directory for PNGs and evidence.json; otherwise temporary outputs are removed")
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="qml-preview-smoke-") as temporary:
        work = Path(temporary)
        evidence = work / "evidence"
        if options.evidence_dir:
            evidence = options.evidence_dir.absolute()
        evidence.mkdir()
        client = Client(work)
        checks, images = [], []

        def passed(name):
            checks.append(name)
            print("PASS:", name)

        def arguments(output="candidate.png", **changes):
            return {"qmlPath": str(FIXTURE), "outputPath": str(work / output),
                    "width": 480, "height": 300, "importPaths": [str(IMPORTS)],
                    "readyProperty": "previewReady", "imageMode": "path", **changes}

        def failure(args, text=None, protocol=False):
            response = client.call(args)
            if protocol:
                assert response["error"]["code"] == -32602, response
            else:
                assert response["result"]["isError"] is True, response
                if text:
                    assert text.lower() in response["result"]["content"][0]["text"].lower(), response
            return response

        try:
            listing = client.request("tools/list")["result"]["tools"]
            assert {tool["name"] for tool in listing} == {"healthcheck", "render_qml", "capture_plugin_page"}
            schema = next(tool["inputSchema"] for tool in listing if tool["name"] == "render_qml")
            assert schema["required"] == ["qmlPath", "outputPath"]
            assert set(schema["properties"]) == {"qmlPath", "outputPath", "width", "height", "dpr", "importPaths", "readyProperty", "timeoutMs", "imageMode", "initialProperties", "locale", "measureObjects", "dependencyPaths", "snapshot", "geometryChecks", "warningsPolicy"}
            passed("initialize, tools/list and advertised schema")

            preflight = client.request("tools/call", {"name": "healthcheck", "arguments": {}})
            assert preflight["result"]["isError"] is False, preflight
            assert preflight["result"]["structuredContent"]["qmlExecuted"] is False
            assert preflight["result"]["structuredContent"]["toolVersion"] == "0.3.0"
            passed("healthcheck reports versions, backend and capabilities without project QML")

            for dpr in (1, 2):
                path = evidence / f"fixture-dpr{dpr}.png"
                response = client.call(arguments(outputPath=str(path), dpr=dpr))
                assert response["result"]["isError"] is False, response
                metadata = response["result"]["structuredContent"]
                assert json.loads(response["result"]["content"][0]["text"]) == metadata
                width, height, pixel = png(path)
                assert (width, height) == (480 * dpr, 300 * dpr)
                assert metadata["dpr"] == dpr and metadata["readiness"] == "property-and-frame"
                assert pixel(2 * dpr, 2 * dpr) == (24, 32, 40)
                assert pixel(100 * dpr, 150 * dpr) == (113, 199, 160)
                assert metadata["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert not any("stale-imports" in p for p in metadata["qtImportPaths"])
                images.append({**metadata, "state": "Fixture ready", "palette": {
                    "background": "#182028", "panel": "#25313c", "text": "#f0f4f8", "accent": "#71c7a0"},
                    "inspected": False, "origin": "local-consumer-fixture", "adapters": "inert QtObject model"})
                passed(f"actual component consumer, delayed readiness, DPR {dpr}, PNG CRC/decode/colors")

            dependency = ROOT / "tests" / "FixturePanel.qml"
            title = "Проверка QML"
            response = client.call(arguments(
                outputPath=str(evidence / "fixture-ru-dpr2.png"), dpr=2, imageMode="image", locale="ru_RU",
                initialProperties={"fixtureTitle": title, "fixtureState": "Готово"},
                measureObjects=["consumer", "panel", "title", "status", "accent"],
                dependencyPaths=[str(dependency)],
            ))
            assert response["result"]["isError"] is False, response
            metadata = response["result"]["structuredContent"]
            attachment = response["result"]["content"][1]
            path = Path(metadata["outputPath"])
            assert attachment["type"] == "image" and attachment["mimeType"] == "image/png"
            assert base64.b64decode(attachment["data"]) == path.read_bytes()
            assert metadata["locale"] == "ru_RU" and metadata["initialProperties"]["fixtureTitle"] == title
            assert metadata["measurements"]["panel"]["width"] == 440
            assert metadata["measurements"]["panel"]["height"] == 260
            assert metadata["measurements"]["panel"]["x"] == 20
            assert metadata["measurements"]["title"]["x"] == 40
            assert metadata["dependencyHashes"][str(dependency)] == hashlib.sha256(dependency.read_bytes()).hexdigest()
            images.append({**metadata, "state": "Готово", "palette": images[0]["palette"], "inspected": False,
                           "origin": "local-consumer-fixture", "adapters": "inert QtObject model"})
            passed("PNG attachment, pre-creation properties, Russian locale, actual item geometry and dependency hashes")

            for changes in ({"imageMode": "bad"}, {"locale": "en-US"}, {"locale": "../../bad"},
                            {"initialProperties": []},
                            {"initialProperties": {"x": "z" * 65536}}, {"qmlPath": "/tmp/\ud800.qml"},
                            {"measureObjects": ["title", "title"]}, {"measureObjects": [None]},
                            {"dependencyPaths": ["relative.qml"]}, {"dependencyPaths": [str(dependency)] * 129}):
                failure(arguments(**changes), protocol=True)
            failure(arguments(measureObjects=["missing-item"]), "exactly one")
            failure(arguments(locale="zz_ZZ"), "locale")
            failure(arguments(initialProperties={"unknownRootProperty": 1}), "initial")
            failure(arguments(dependencyPaths=[str(work / "missing-dependency")]))
            passed("new option validation and missing measurement/property/locale/dependency errors")

            mutable = work / "mutable.txt"
            mutable.write_text("before", encoding="utf-8")
            stable = work / "stable.qml"
            stable.write_text('import QtQuick\nRectangle { property bool previewReady: false; Timer { interval: 500; running: true; onTriggered: parent.previewReady = true } }', encoding="utf-8")
            def mutate():
                time.sleep(0.25)
                mutable.write_text("after", encoding="utf-8")
            mutation = threading.Thread(target=mutate)
            mutation.start()
            try:
                failure(arguments(qmlPath=str(stable), dependencyPaths=[str(mutable)]), "changed during")
            finally:
                mutation.join()
            assert not (work / "candidate.png").exists()
            passed("dependency mutation during rendering refuses publication")

            for changes in ({"width": 0}, {"height": -1}, {"width": True}, {"width": 1.5},
                            {"width": 4097}, {"width": 4096, "height": 4096}, {"dpr": 3},
                            {"dpr": True}, {"dpr": 1.5}, {"timeoutMs": 99}, {"timeoutMs": 10001},
                            {"qmlPath": "relative.qml"}, {"outputPath": "relative.png"},
                            {"qmlPath": str(work / ".." / "fixture.qml")}, {"readyProperty": ""},
                            {"importPaths": "oops"}, {"importPaths": ["relative"]},
                            {"importPaths": [None]}, {"importPaths": [str(IMPORTS)] * 33}, {"unknown": 1}):
                failure(arguments(**changes), protocol=True)
            failure({"qmlPath": str(FIXTURE)}, protocol=True)
            failure([], protocol=True)
            passed("schema bounds, unknown fields, required paths and pixel budget")

            failure(arguments(qmlPath=str(work / "missing.qml")), "existing")
            failure(arguments(importPaths=[]), "FixturePalette")
            failure(arguments(importPaths=[str(work / "missing-imports")]), "No such")
            malformed = work / "broken.qml"
            malformed.write_text("import QtQuick\nRectangle { bad syntax", encoding="utf-8")
            failure(arguments(qmlPath=str(malformed)), "Renderer exited")
            unsupported = work / "window.qml"
            unsupported.write_text("import QtQuick\nWindow { visible: true }", encoding="utf-8")
            failure(arguments(qmlPath=str(unsupported)), "QQuickItem")
            failure(arguments(readyProperty="missingReady"), "Missing root")
            wrong_ready = work / "wrong-ready.qml"
            wrong_ready.write_text('import QtQuick\nItem { property string previewReady: "true" }', encoding="utf-8")
            failure(arguments(qmlPath=str(wrong_ready)), "boolean")
            passed("missing/malformed QML, imports, unsupported root and readiness contract")

            never = work / "never-ready.qml"
            never.write_text("import QtQuick\nRectangle { property bool previewReady: false }", encoding="utf-8")
            failure(arguments(qmlPath=str(never), timeoutMs=150), "Timed out")
            assert not (work / "candidate.png").exists()
            blocked = work / "blocked.qml"
            blocked.write_text("import QtQuick\nItem { Component.onCompleted: { while (true) {} } }", encoding="utf-8")
            failure(arguments(qmlPath=str(blocked), timeoutMs=100), "process deadline")
            passed("readiness timeout and hard deadline for blocked QML; no output on failure")

            client.request_id += 1
            cancelled_id = client.request_id
            client.write({"jsonrpc": "2.0", "id": cancelled_id, "method": "tools/call",
                          "params": {"name": "render_qml", "arguments": arguments(qmlPath=str(blocked), timeoutMs=10000)}})
            time.sleep(0.15)
            client.write({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": cancelled_id}})
            assert client.request("ping")["result"] == {}
            response = client.call(arguments("after-cancel.png"))
            assert response["result"]["isError"] is False, response
            assert not (work / "candidate.png").exists()
            passed("in-flight cancellation, responsive ping and subsequent render")

            shutting_down = Client(work)
            shutting_down.write({"jsonrpc": "2.0", "id": 90, "method": "tools/call", "params": {
                "name": "render_qml", "arguments": arguments("eof.png", qmlPath=str(blocked), timeoutMs=10000)}})
            time.sleep(0.15)
            start = time.monotonic()
            shutting_down.close()
            assert time.monotonic() - start < 3 and not (work / "eof.png").exists()
            terminating = Client(work)
            terminating.write({"jsonrpc": "2.0", "id": 91, "method": "tools/call", "params": {
                "name": "render_qml", "arguments": arguments("term.png", qmlPath=str(blocked), timeoutMs=10000)}})
            time.sleep(0.15)
            terminating.process.terminate()
            terminating.close()
            assert not (work / "term.png").exists()
            passed("EOF and SIGTERM cancel active renderer and stop the server within bounds")

            original = images[0]["sha256"]
            failure(arguments(outputPath=images[0]["outputPath"]), "already exists")
            assert hashlib.sha256(Path(images[0]["outputPath"]).read_bytes()).hexdigest() == original
            link = work / "link.png"
            link.symlink_to(work / "missing-target.png")
            failure(arguments(outputPath=str(link)), "already exists")
            parent_link = work / "linked-parent"
            parent_link.symlink_to(evidence, target_is_directory=True)
            failure(arguments(outputPath=str(parent_link / "new.png")))
            failure(arguments(outputPath=str(work / "missing-parent" / "new.png")))
            failure(arguments(outputPath=str(work / "wrong.jpg")), ".png")
            failure(arguments(outputPath=str(evidence)), ".png")
            locked = work / "locked"
            locked.mkdir(mode=0o500)
            try:
                failure(arguments(outputPath=str(locked / "new.png")), "Permission")
            finally:
                locked.chmod(0o700)
            passed("no overwrite, dangling/ancestor symlinks, missing parent, extension and permissions")

            # Verify the publish-time guard, not merely the initial exists check.
            spec = importlib.util.spec_from_file_location("qml_preview", ROOT / "mcp-qml-preview.py")
            wrapper = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wrapper)
            parent, name = wrapper.destination(str(work / "race.png"))
            try:
                (work / "race.png").write_bytes(b"preserve me")
                try:
                    wrapper.publish(b"replacement", parent, name)
                    raise AssertionError("Late collision replaced existing data")
                except FileExistsError:
                    pass
                assert (work / "race.png").read_bytes() == b"preserve me"
                assert not list(work.glob(".qml-preview-*"))
            finally:
                os.close(parent)
            passed("publish-time collision preserves original and cleans temporary file")

            old_limit = wrapper.MAX_IMAGE
            wrapper.MAX_IMAGE = 1
            try:
                try:
                    wrapper.render(wrapper.validate(arguments("attachment-limit.png", imageMode="image")),
                                   threading.Event(), threading.Lock())
                    raise AssertionError("Oversized attachment accepted")
                except ValueError as exc:
                    assert "attachment limit" in str(exc)
                assert not (work / "attachment-limit.png").exists()
            finally:
                wrapper.MAX_IMAGE = old_limit
            passed("attachment limit is enforced before publication on the actual renderer path")

            # Both source and binary may be moved together without home paths.
            relocated = work / "relocated"
            relocated.mkdir()
            for filename in ("mcp-qml-preview.py", "qml-render"):
                shutil.copy2(ROOT / filename, relocated / filename)
            portable = Client(work, wrapper=relocated / "mcp-qml-preview.py")
            try:
                response = portable.call(arguments("portable.png"))
                assert response["result"]["isError"] is False, response
                assert png(work / "portable.png")[:2] == (480, 300)
            finally:
                portable.close()
            passed("relocated wrapper/binary pair, launched from another working directory")

            (relocated / "qml-render").unlink()
            unavailable = Client(work, wrapper=relocated / "mcp-qml-preview.py")
            try:
                response = unavailable.call(arguments("unavailable.png"))
                assert response["result"]["isError"] is True, response
                assert not (work / "unavailable.png").exists()
                assert unavailable.request("ping")["result"] == {}
            finally:
                unavailable.close()
            passed("missing sibling renderer is a tool error without output; server remains usable")

            crash_renderer = relocated / "qml-render"
            crash_renderer.write_text('#!/usr/bin/env python3\nimport os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n')
            crash_renderer.chmod(0o700)
            crashing = Client(work, wrapper=relocated / "mcp-qml-preview.py")
            try:
                response = crashing.call(arguments("crash.png"))
                assert response["result"]["isError"] is True
                assert "Renderer exited -9" in response["result"]["content"][0]["text"]
                assert not (work / "crash.png").exists()
                assert crashing.request("ping")["result"] == {}
            finally:
                crashing.close()
            passed("abnormally killed owned renderer produces a tool error, no image, and a usable server")

            simple = work / "simple.qml"
            simple.write_text('import QtQuick\nRectangle { color: "#182028" }', encoding="utf-8")
            defaults = client.call({"qmlPath": str(simple), "outputPath": str(work / "defaults.png")})
            assert defaults["result"]["isError"] is False, defaults
            assert defaults["result"]["structuredContent"]["readiness"] == "loaded-frame"
            assert png(work / "defaults.png")[:2] == (480, 360)
            for n in range(3):
                response = client.call(arguments(f"repeat-{n}.png"))
                assert response["result"]["isError"] is False, response
            passed("default geometry, loaded-frame mode and repeated calls after failures")

            for raw, code in ((b"{broken\n", -32700), (b"[]\n", -32600),
                              (b'{"jsonrpc":"2.0","id":1,"method":"ping","params":NaN}\n', -32700),
                              (b"[" * 2000 + b"\n", -32700), (b"x" * (1024 * 1024 + 1) + b"\n", -32700)):
                client.process.stdin.write(raw)
                client.process.stdin.flush()
                assert client.read()["error"]["code"] == code
            assert client.request("ping")["result"] == {}
            assert client.request("unknown")["error"]["code"] == -32601
            assert client.request("tools/call", {"name": "unknown"})["error"]["code"] == -32602
            assert client.request("tools/call", [1])["error"]["code"] == -32602
            passed("JSON-RPC error framing and stream recovery after malformed/oversized requests")

            assert client.request("ping", {"unused": True})["error"]["code"] == -32602
            assert client.request("tools/call", {"name": "healthcheck", "arguments": {"unexpected": 1}})["error"]["code"] == -32602
            passed("strict ping and healthcheck argument contract")

            warnings = work / "warnings.qml"
            warnings.write_text('import QtQuick\nRectangle { Component.onCompleted: console.warn("fixture diagnostic") }', encoding="utf-8")
            response = client.call({"qmlPath": str(warnings), "outputPath": str(work / "warnings.png")})
            assert response["result"]["isError"] is False, response
            assert "fixture diagnostic" in response["result"]["structuredContent"]["diagnostics"]
            passed("QML diagnostics stay out of JSON-RPC stdout and are returned with metadata")
        finally:
            client.close()

        latest = Client(work, "2025-11-25")
        try:
            result = latest.request("tools/call", {"name": "healthcheck"})
            assert result["result"]["isError"] is False and "structuredContent" in result["result"]
            passed("2025-11-25 protocol compatibility")
        finally:
            latest.close()

        legacy = Client(work, "2024-11-05")
        try:
            response = legacy.call({"qmlPath": str(simple), "outputPath": str(work / "legacy.png")})
            assert response["result"]["isError"] is False and "structuredContent" not in response["result"]
            assert json.loads(response["result"]["content"][0]["text"])["pixelWidth"] == 480
            passed("2024-11-05 compatibility with JSON text metadata")
        finally:
            legacy.close()

        evidence_data = {
            "checks": checks, "images": images,
            "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (ROOT / "mcp-qml-preview.py", ROOT / "qml-render.cpp", ROOT / "qml-render",
                                  ROOT / "Makefile", ROOT / "tests" / "smoke.py", FIXTURE,
                                  ROOT / "tests" / "FixturePanel.qml", IMPORTS / "FixturePalette" / "qmldir",
                                  IMPORTS / "FixturePalette" / "Colors.qml")},
            "consumerScope": "Bundled actual FixturePanel consumer, not an Omarchy/Home Organizer consumer",
            "clientScope": "Owned stdio smoke client; current OpenCode attachment NOT VERIFIED",
            "review": "Direct self-review; no independent review",
        }
        (evidence / "evidence.json").write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
        print(f"PASS: {len(checks)} check groups; evidence: {evidence}")


if __name__ == "__main__":
    main()
