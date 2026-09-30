#!/usr/bin/env python3
"""Actual OpenCode MCP acceptance with a local scripted provider, no model calls."""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    options = parser.parse_args()
    evidence = options.evidence_dir.absolute()
    evidence.mkdir()
    requests, failures = [], []
    with tempfile.TemporaryDirectory(prefix="qml-preview-client-") as temporary:
        work = Path(temporary)
        project = work / "project"
        config = work / "opencode-config"
        for directory in (project, config, work / "home", work / "data", work / "cache", work / "state"):
            directory.mkdir()
        for filename in ("fixture.qml", "FixturePanel.qml"):
            shutil.copy2(ROOT / "tests" / filename, project / filename)
        (project / "manifest.json").write_text(json.dumps({"kinds": ["bar-widget"], "entryPoints": {"bar-widget": "fixture.qml"}}))
        (project / "AGENTS.md").write_text("This is an isolated MCP transport test with an inert QML consumer. No desktop access.\n")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    requests.append(body)
                    tools = {entry["function"]["name"] for entry in body.get("tools", [])}
                    def tool(suffix):
                        matches = [name for name in tools if name.endswith(suffix)]
                        assert len(matches) == 1, (suffix, sorted(tools))
                        return matches[0]
                    step = len(requests) - 1
                    if step == 0:
                        name, args = tool("healthcheck"), {}
                    elif step == 1:
                        name, args = "edit", {"filePath": str(project / "fixture.qml"),
                                              "oldString": 'property string fixtureState: "Fixture ready"',
                                              "newString": 'property string fixtureState: "Reviewed state"'}
                        assert name in tools
                    elif step == 2:
                        name, args = tool("render_qml"), {
                            "qmlPath": str(project / "fixture.qml"), "outputPath": str(evidence / "client.png"),
                            "width": 480, "height": 300, "dpr": 2,
                            "importPaths": [str(ROOT / "tests" / "imports")], "readyProperty": "previewReady",
                            "imageMode": "image", "locale": "en_US", "measureObjects": ["panel"],
                            "dependencyPaths": [str(project / "FixturePanel.qml")],
                        }
                    elif step == 3:
                        name, args = tool("render_qml"), {
                            "qmlPath": str(project / "missing.qml"), "outputPath": str(evidence / "must-not-exist.png")}
                    else:
                        name, args = None, None
                    message = {"role": "assistant", "content": "Client smoke completed."}
                    if name:
                        message["content"] = None
                        message["tool_calls"] = [{"id": f"fixture-call-{step}", "type": "function",
                                                  "function": {"name": name, "arguments": json.dumps(args)}}]
                    self.send_response(200)
                    streaming = body.get("stream", False)
                    self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
                    self.end_headers()
                    if streaming:
                        delta = {"role": "assistant"}
                        if name:
                            delta["tool_calls"] = [{"index": 0, **message["tool_calls"][0]}]
                        else:
                            delta["content"] = message["content"]
                        chunks = [
                            {"id": "smoke", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
                             "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                            {"id": "smoke", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
                             "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if name else "stop"}]},
                        ]
                        for chunk in chunks:
                            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                        self.wfile.write(b"data: [DONE]\n\n")
                    else:
                        self.wfile.write(json.dumps({"id": "smoke", "object": "chat.completion", "created": 1,
                                                    "model": "fixture", "choices": [{"index": 0, "message": message,
                                                                                     "finish_reason": "tool_calls" if name else "stop"}],
                                                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}).encode())
                    self.wfile.flush()
                except Exception as exc:
                    failures.append(repr(exc))
                    self.send_error(500, "Scripted fixture failed")

        http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        http.daemon_threads = True
        server = threading.Thread(target=http.serve_forever, daemon=True)
        server.start()
        fixture_config = {
            "$schema": "https://opencode.ai/config.json", "model": "preview-test/fixture",
            "small_model": "preview-test/fixture", "snapshot": False, "share": "disabled",
            "autoupdate": False, "enabled_providers": ["preview-test"], "permission": "allow",
            "plugin": [(ROOT / "integrations" / "opencode-visual-cycle.mjs").as_uri()],
            "mcp": {"qml-preview": {"type": "local", "command": ["python3", str(ROOT / "mcp-qml-preview.py")],
                                    "enabled": True, "timeout": 15000}},
            "provider": {"preview-test": {"npm": "@ai-sdk/openai-compatible", "name": "Local scripted fixture",
                                          "options": {"baseURL": f"http://127.0.0.1:{http.server_port}/v1", "apiKey": "fixture-only"},
                                          "models": {"fixture": {"name": "Fixture", "attachment": True,
                                                                 "modalities": {"input": ["text", "image"], "output": ["text"]},
                                                                 "limit": {"context": 128000, "output": 4096}}}}},
        }
        (config / "opencode.json").write_text(json.dumps(fixture_config))
        env = {**os.environ, "HOME": str(work / "home"), "XDG_CONFIG_HOME": str(work / "home" / ".config"),
               "XDG_DATA_HOME": str(work / "data"), "XDG_CACHE_HOME": str(work / "cache"), "XDG_STATE_HOME": str(work / "state"),
               "OPENCODE_CONFIG_DIR": str(config), "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
               "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
               "OPENCODE_DISABLE_MODELS_FETCH": "1", "NO_COLOR": "1", "PWD": str(project)}
        for key in ("OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_SERVER_PASSWORD"):
            env.pop(key, None)
        command = ["opencode", "--print-logs", "run", "--dir", str(project), "--format", "json", "--model", "preview-test/fixture", "--title", "QML MCP acceptance",
                   "Execute only the fixed local fixture calls supplied by the scripted transport test."]
        try:
            result = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, timeout=90)
        finally:
            http.shutdown()
            http.server_close()
            server.join(timeout=3)
        (evidence / "client-stdout.jsonl").write_text(result.stdout)
        (evidence / "client-stderr.txt").write_text(result.stderr)
        (evidence / "provider-requests.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2))
        assert result.returncode == 0, result.stderr[-4000:]
        assert not failures, failures
        assert 5 <= len(requests) <= 7, f"Unexpected provider calls: {len(requests)}"
        all_messages = json.dumps(requests, ensure_ascii=False)
        assert "Plugin visual acceptance" in all_messages, "System hook did not reach actual client"
        assert "Plugin visual checkpoint" in all_messages, "Edit reminder did not reach actual client"
        assert "existing .qml file" in all_messages, "Tool error did not reach actual client"
        assert any("rendererVersion" in str(message.get("content")) and "0.2.0" in str(message.get("content"))
                   for request in requests for message in request["messages"])
        assert "data:image/png;base64," in all_messages, "PNG attachment did not reach image-capable provider input"
        png = (evidence / "client.png").read_bytes()
        assert base64.b64encode(png).decode() in all_messages, "Provider received a different PNG"
        assert not (evidence / "must-not-exist.png").exists()
        report = {"client": subprocess.check_output(["opencode", "--version"], text=True).strip(),
                  "provider": "Local deterministic scripted HTTP fixture; no model/API calls", "requests": len(requests),
                  "checks": ["MCP initialize/list/call", "healthcheck", "PNG image attachment delivered to provider input",
                             "tool error delivered", "system hook", "UI edit reminder"],
                  "image": str(evidence / "client.png"), "inspected": False,
                  "scope": "Actual isolated OpenCode process, not the user's active session"}
        (evidence / "client-evidence.json").write_text(json.dumps(report, indent=2) + "\n")
        print("PASS: actual OpenCode MCP calls, PNG delivery, errors, system context and edit reminders; no model inference")


if __name__ == "__main__":
    main()
