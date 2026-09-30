#!/usr/bin/env python3
"""Local stdio MCP server for reviewed Qt Quick fixtures."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time

VERSION = "0.3.0"
PROTOCOLS = ("2024-11-05", "2025-06-18", "2025-11-25")
MODERN_PROTOCOL = "2026-07-28"
RENDERER = Path(__file__).resolve().with_name("qml-render")
MAX_MESSAGE = 1024 * 1024
MAX_PNG = 64 * 1024 * 1024
MAX_IMAGE = 4 * 1024 * 1024
MAX_SOURCE = 16 * 1024 * 1024
MAX_METADATA = 512 * 1024
SEND_LOCK = threading.Lock()
NAME_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 128}
NUMBER_SCHEMA = {"type": "number", "minimum": -1000000, "maximum": 1000000}
CHECK_FIELDS = {
    "align": ("a", "b", "field"), "equal": ("a", "b", "field"),
    "centered": ("a", "container", "axis"), "symmetric": ("a", "b", "container", "axis"),
    "inside": ("a", "container"), "noOverlap": ("a", "b"),
    "size": ("a", "field", "value"), "gap": ("a", "b", "axis", "value"),
}


def check_schema(kind, fields):
    properties = {"kind": {"const": kind}, "id": NAME_SCHEMA,
                  "tolerance": {"type": "number", "minimum": 0, "maximum": 1000, "default": 1}}
    for name in fields:
        if name == "field":
            choices = ["width", "height"] if kind in ("equal", "size") else ["left", "right", "top", "bottom", "centerX", "centerY"]
            properties[name] = {"type": "string", "enum": choices}
        elif name == "axis":
            properties[name] = {"type": "string", "enum": ["x", "y"]}
        else:
            properties[name] = NUMBER_SCHEMA if name == "value" else NAME_SCHEMA
    return {"type": "object", "properties": properties, "required": ["kind", *fields], "additionalProperties": False}


SCHEMA = {
    "type": "object",
    "properties": {
        "qmlPath": {"type": "string", "minLength": 1, "maxLength": 4096,
                    "description": "Absolute path to a reviewed local QQuickItem-root QML fixture."},
        "outputPath": {"type": "string", "minLength": 1, "maxLength": 4096,
                       "description": "Absolute path to a new PNG; existing files and symlink destinations are refused."},
        "width": {"type": "integer", "minimum": 1, "maximum": 4096, "default": 480,
                  "description": "Logical width; width * height * dpr squared must not exceed 16,000,000 pixels."},
        "height": {"type": "integer", "minimum": 1, "maximum": 4096, "default": 360,
                   "description": "Logical height, independent of pixel density."},
        "dpr": {"type": "integer", "enum": [1, 2], "default": 1},
        "importPaths": {"type": "array", "maxItems": 32, "default": [],
                        "items": {"type": "string", "minLength": 1, "maxLength": 4096},
                        "description": "Absolute project import directories, highest priority first; no environment or mock imports."},
        "readyProperty": {"type": "string", "minLength": 1, "maxLength": 128,
                          "description": "Optional root boolean property that must become true before rendering a frame."},
        "timeoutMs": {"type": "integer", "minimum": 100, "maximum": 10000, "default": 5000},
        "imageMode": {"type": "string", "enum": ["image", "path"], "default": "image",
                      "description": "image returns a PNG attachment (maximum 4 MiB PNG); path returns metadata for host image-reading tools."},
        "initialProperties": {"type": "object", "default": {}, "maxProperties": 64,
                              "description": "Root properties applied before creation; JSON values only, maximum 64 KiB encoded."},
        "locale": {"type": "string", "minLength": 1, "maxLength": 32,
                   "pattern": "^(C|[a-z]{2,3}(_[A-Z][a-z]{3})?(_[A-Z]{2}|_[0-9]{3})?)$",
                   "description": "Explicit Qt locale, e.g. ru_RU or en_US; no translation catalog is installed automatically."},
        "measureObjects": {"type": "array", "default": [], "maxItems": 64, "uniqueItems": True,
                           "items": {"type": "string", "minLength": 1, "maxLength": 128},
                           "description": "Unique objectName values of visual items to measure in logical scene coordinates."},
        "dependencyPaths": {"type": "array", "default": [], "maxItems": 128, "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1, "maxLength": 4096},
                            "description": "Explicit reviewed files (QML, models, catalogs, assets) hashed before and after rendering; maximum 16 MiB per file."},
        "geometryChecks": {"type": "array", "default": [], "maxItems": 64,
                           "items": {"oneOf": [check_schema(k, f) for k, f in CHECK_FIELDS.items()]},
                           "description": "Explicit logical-scene layout rules; default tolerance 1. Failed rules retain PNG with isError=true."},
        "snapshot": {"type": "object", "default": {}, "properties": {
            "maxDepth": {"type": "integer", "minimum": 0, "maximum": 16, "default": 6},
            "maxItems": {"type": "integer", "minimum": 1, "maximum": 256, "default": 64}},
            "additionalProperties": False,
            "description": "Opt-in visual-tree snapshot; omit for no snapshot, {} enables bounded defaults. Not an accessibility consumer test."},
        "warningsPolicy": {"type": "string", "enum": ["report", "error"], "default": "report",
                           "description": "error marks warning/critical diagnostics as acceptance errors while retaining the verified PNG."},
    },
    "required": ["qmlPath", "outputPath"],
    "additionalProperties": False,
}


class InvalidParams(ValueError):
    pass


class Cancelled(RuntimeError):
    pass


class ToolFailure(RuntimeError):
    def __init__(self, code, message, hint):
        super().__init__(message)
        self.code, self.hint = code, hint


def validate_checks(checks):
    if not isinstance(checks, list) or len(checks) > 64:
        raise InvalidParams("geometryChecks must be an array of at most 64 rules")
    for rule in checks:
        if not isinstance(rule, dict) or not isinstance(rule.get("kind"), str) or rule["kind"] not in CHECK_FIELDS:
            raise InvalidParams("Unknown geometry rule")
        spec = check_schema(rule["kind"], CHECK_FIELDS[rule["kind"]])
        if set(rule) - spec["properties"].keys() or any(key not in rule for key in spec["required"]):
            raise InvalidParams("Missing/unknown geometry rule fields")
        for name, value in rule.items():
            field = spec["properties"][name]
            if field.get("type") == "number":
                if type(value) not in (int, float) or not math.isfinite(value) or not field["minimum"] <= value <= field["maximum"]:
                    raise InvalidParams(f"Invalid geometry number: {name}")
            elif not valid_string(value, 1, 128) or "enum" in field and value not in field["enum"]:
                raise InvalidParams(f"Invalid geometry field: {name}")
        if rule["kind"] == "size" and rule["value"] < 0:
            raise InvalidParams("Expected size must be nonnegative")
    return checks


def geometry_results(checks, measurements):
    results = []
    def edge(item, field):
        return {"left": item["x"], "right": item["x"] + item["width"],
                "top": item["y"], "bottom": item["y"] + item["height"],
                "centerX": item["x"] + item["width"] / 2,
                "centerY": item["y"] + item["height"] / 2,
                "width": item["width"], "height": item["height"]}[field]
    for index, rule in enumerate(checks):
        tolerance = rule.get("tolerance", 1)
        names = [rule[key] for key in ("a", "b", "container") if key in rule]
        missing = [name for name in names if name not in measurements]
        result = {"id": rule.get("id", str(index)), "kind": rule["kind"], "tolerance": tolerance}
        if missing:
            results.append({**result, "status": "FAIL", "expected": "unique visual objects", "measured": {"missing": missing}})
            continue
        a = measurements[rule["a"]]
        b = measurements.get(rule.get("b"))
        c = measurements.get(rule.get("container"))
        if any(not measurements[name]["visible"] or measurements[name]["width"] <= 0 or measurements[name]["height"] <= 0 for name in names):
            results.append({**result, "status": "FAIL", "expected": "visible positive-area objects", "measured": names})
            continue
        kind = rule["kind"]
        if kind in ("align", "equal"):
            expected, measured = edge(b, rule["field"]), edge(a, rule["field"])
            delta = abs(measured - expected)
        elif kind == "size":
            expected, measured = rule["value"], edge(a, rule["field"])
            delta = abs(measured - expected)
        elif kind == "centered":
            field = "centerX" if rule["axis"] == "x" else "centerY"
            expected, measured = edge(c, field), edge(a, field)
            delta = abs(measured - expected)
        elif kind == "symmetric":
            axis = rule["axis"]
            field, cross, dimension, other = ("centerX", "centerY", "width", "height") if axis == "x" else ("centerY", "centerX", "height", "width")
            expected = [2 * edge(c, field), edge(a, cross), a[dimension], a[other]]
            measured = [edge(a, field) + edge(b, field), edge(b, cross), b[dimension], b[other]]
            delta = max(abs(x - y) for x, y in zip(expected, measured))
        elif kind == "inside":
            expected = "all bounds inside container"
            measured = {"left": edge(c, "left") - edge(a, "left"), "right": edge(a, "right") - edge(c, "right"),
                        "top": edge(c, "top") - edge(a, "top"), "bottom": edge(a, "bottom") - edge(c, "bottom")}
            delta = max(0, *measured.values())
        elif kind == "noOverlap":
            expected = "intersection penetration <= tolerance"
            measured = {"x": max(0, min(edge(a, "right"), edge(b, "right")) - max(a["x"], b["x"])),
                        "y": max(0, min(edge(a, "bottom"), edge(b, "bottom")) - max(a["y"], b["y"]))}
            delta = min(measured.values())
        else:  # directed gap, a precedes b
            expected = rule["value"]
            measured = b[rule["axis"]] - edge(a, "right" if rule["axis"] == "x" else "bottom")
            delta = abs(measured - expected)
        results.append({**result, "status": "PASS" if delta <= tolerance else "FAIL", "expected": expected,
                        "measured": measured, "deviation": delta, "coordinateSpace": "logical-scene-axis-aligned"})
    return results


def valid_string(value, low=1, high=4096):
    if not isinstance(value, str) or not low <= len(value) <= high or "\0" in value:
        return False
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False


def validate(args):
    if not isinstance(args, dict) or set(args) - SCHEMA["properties"].keys():
        raise InvalidParams("Arguments must be an object with only advertised properties")
    result = {}
    for name, spec in SCHEMA["properties"].items():
        if name not in args:
            if name in SCHEMA["required"]:
                raise InvalidParams(f"Missing argument: {name}")
            if "default" not in spec:
                continue
        value = args.get(name, spec.get("default"))
        if name == "geometryChecks":
            result[name] = validate_checks(value)
            continue
        if name == "snapshot":
            if not isinstance(value, dict) or set(value) - {"maxDepth", "maxItems"}:
                raise InvalidParams("snapshot accepts only maxDepth and maxItems")
            for key, limit in (("maxDepth", 16), ("maxItems", 256)):
                if key in value and (type(value[key]) is not int or not (0 if key == "maxDepth" else 1) <= value[key] <= limit):
                    raise InvalidParams(f"Invalid snapshot {key}")
            result[name] = value if name in args else None
            continue
        if spec["type"] == "integer":
            if type(value) is not int or not spec.get("minimum", 1) <= value <= spec.get("maximum", 2):
                raise InvalidParams(f"Invalid integer: {name}")
            if "enum" in spec and value not in spec["enum"]:
                raise InvalidParams(f"Unsupported {name}")
        elif spec["type"] == "string":
            if not valid_string(value, spec.get("minLength", 1), spec.get("maxLength", 4096)):
                raise InvalidParams(f"Invalid string: {name}")
            if "enum" in spec and value not in spec["enum"]:
                raise InvalidParams(f"Unsupported {name}")
            if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
                raise InvalidParams(f"Invalid format: {name}")
        elif spec["type"] == "array":
            if not isinstance(value, list) or len(value) > spec["maxItems"]:
                raise InvalidParams(f"Invalid array: {name}")
            if any(not valid_string(p, 1, spec["items"]["maxLength"]) for p in value):
                raise InvalidParams(f"Invalid array item: {name}")
            if spec.get("uniqueItems") and len(set(value)) != len(value):
                raise InvalidParams(f"Duplicate array item: {name}")
        else:
            if not isinstance(value, dict) or len(value) > spec["maxProperties"]:
                raise InvalidParams("initialProperties must be an object with at most 64 root properties")
            if any(not valid_string(key, 1, 128) for key in value):
                raise InvalidParams("Invalid root property name")
            try:
                encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                raise InvalidParams("initialProperties must contain finite JSON values and valid Unicode") from exc
            if len(encoded) > 65536:
                raise InvalidParams("initialProperties exceeds 64 KiB")
        result[name] = value
    if result["width"] * result["height"] * result["dpr"] ** 2 > 16_000_000:
        raise InvalidParams("Render exceeds 16,000,000 physical pixels")
    for name in ("qmlPath", "outputPath"):
        if not Path(result[name]).is_absolute() or ".." in Path(result[name]).parts:
            raise InvalidParams(f"{name} must be absolute without '..'")
    for path in result["importPaths"] + result["dependencyPaths"]:
        if not Path(path).is_absolute() or ".." in Path(path).parts:
            raise InvalidParams("Import/dependency paths must be absolute without '..'")
    names = set(result["measureObjects"])
    for rule in result["geometryChecks"]:
        names.update(rule[k] for k in ("a", "b", "container") if k in rule)
    if len(names) > 128:
        raise InvalidParams("Measurements and checks reference more than 128 objects")
    return result


def destination(path):
    """Pin the parent directory without following symlinks, including ancestors."""
    parts = Path(path).parts
    if path.endswith("/") or len(parts) < 2 or Path(path).suffix.lower() != ".png":
        raise ValueError("outputPath must name a new .png file")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        try:
            os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return fd, parts[-1]
        raise FileExistsError("Output already exists (including symlinks)")
    except BaseException:
        os.close(fd)
        raise


def publish(data, parent, name):
    """Publish a complete PNG with an exclusive hard link, never replace a file."""
    temporary = ".qml-preview-" + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=parent)


def file_hash(path):
    if not Path(path).is_file():
        raise ValueError(f"Dependency must be a regular file: {path}")
    with open(path, "rb") as stream:
        data = stream.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise ValueError(f"Source/dependency exceeds 16 MiB: {path}")
    return hashlib.sha256(data).hexdigest()


def run_renderer(command, args, cancelled, timeout, image=None):
    """Bounded subprocess with cancellation, bounded disk output and owned cleanup."""
    env = os.environ.copy()
    for key in ("QML_IMPORT_PATH", "QML2_IMPORT_PATH", "QT_SCREEN_SCALE_FACTORS", "QT_SCALE_FACTOR"):
        env.pop(key, None)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            pass_fds=() if image is None else (image.fileno(),), env=env, start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        payload = None if args is None else json.dumps(args).encode()
        try:
            while True:
                if cancelled.is_set():
                    raise Cancelled("Render cancelled")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Renderer exceeded its process deadline")
                if os.fstat(stdout.fileno()).st_size > MAX_METADATA or os.fstat(stderr.fileno()).st_size > 65536:
                    raise RuntimeError("Renderer diagnostics/metadata exceed limits")
                if image is not None and os.fstat(image.fileno()).st_size > MAX_PNG:
                    raise RuntimeError("Renderer PNG exceeds 64 MiB")
                try:
                    process.communicate(payload, timeout=min(0.05, max(0.001, deadline - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    payload = None
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
        stderr.seek(0)
        diagnostics = stderr.read(65537).decode("utf-8", errors="replace")
        stdout.seek(0)
        raw = stdout.read(MAX_METADATA + 1)
        if len(raw) > MAX_METADATA or len(diagnostics.encode("utf-8")) > 65536:
            raise RuntimeError("Renderer metadata/diagnostics exceed limits")
        if process.returncode:
            raise RuntimeError(f"Renderer exited {process.returncode}: {diagnostics.strip()}")
        metadata = json.loads(raw)
        if not isinstance(metadata, dict):
            raise RuntimeError("Renderer metadata must be an object")
        if metadata.get("rendererVersion") != VERSION:
            raise ToolFailure("VERSION_MISMATCH", "Renderer/wrapper version mismatch", "Run make with the current sources beside the wrapper")
        return metadata, diagnostics.strip()


def healthcheck(cancelled, timeout=3):
    metadata, diagnostics = run_renderer([str(RENDERER), "--healthcheck"], None, cancelled, timeout)
    if metadata.get("backend") != "software" or metadata.get("platform") != "offscreen":
        raise RuntimeError("Renderer healthcheck returned an unsupported backend/platform")
    metadata.update({"toolVersion": VERSION, "pythonVersion": sys.version.split()[0],
                     "rendererSha256": file_hash(RENDERER), "diagnostics": diagnostics,
                     "limits": {"maxPixels": 16_000_000, "maxPngBytes": MAX_PNG,
                                "maxImageBytes": MAX_IMAGE, "maxQueuedCalls": 8}})
    return metadata, None


def render(args, cancelled, publication_lock):
    deadline = time.monotonic() + args["timeoutMs"] / 1000 + 2
    qml = Path(args["qmlPath"])
    if qml.suffix.lower() != ".qml" or not qml.is_file():
        raise ValueError("qmlPath must be an existing .qml file")
    args["qmlPath"] = str(qml.resolve(strict=True))
    dependencies = {str(Path(p).resolve(strict=True)) for p in args["dependencyPaths"]}
    dependencies.add(args["qmlPath"])
    hashes = {p: file_hash(p) for p in sorted(dependencies)}
    # Refuse a stale binary before executing any owning QML. Hashes also cover
    # changes during preflight, which is part of this invocation's snapshot.
    remaining = deadline - time.monotonic()
    if remaining <= 0 or cancelled.is_set():
        raise TimeoutError("Preflight exceeded its process deadline or call was cancelled")
    healthcheck(cancelled, min(3, remaining))
    args["importPaths"] = [str(Path(p).resolve(strict=True)) for p in args["importPaths"]]
    if any(not Path(p).is_dir() for p in args["importPaths"]):
        raise ValueError("Each import path must be a directory")
    parent, name = destination(args["outputPath"])
    try:
        with tempfile.TemporaryFile() as image:
            renderer_args = dict(args)
            renderer_args["measureObjects"] = sorted(set(args["measureObjects"]) | {
                rule[key] for rule in args["geometryChecks"] for key in ("a", "b", "container") if key in rule})
            renderer_args["requiredMeasureObjects"] = args["measureObjects"]
            renderer_args["expectedVersion"] = VERSION
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Preflight exceeded its process deadline")
            metadata, diagnostics = run_renderer(
                [str(RENDERER), "--output-fd", str(image.fileno())], renderer_args,
                cancelled, remaining, image,
            )
            image.seek(0)
            data = image.read(MAX_PNG + 1)
        expected = (args["width"] * args["dpr"], args["height"] * args["dpr"])
        if len(data) < 33 or len(data) > MAX_PNG or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
            raise RuntimeError("Renderer did not produce a bounded PNG")
        if struct.unpack(">II", data[16:24]) != expected:
            raise RuntimeError("PNG dimensions do not match the requested geometry and DPR")
        if (not isinstance(metadata, dict) or metadata.get("pixelWidth") != expected[0]
                or metadata.get("pixelHeight") != expected[1] or metadata.get("dpr") != args["dpr"]
                or metadata.get("backend") != "software" or metadata.get("platform") != "offscreen"):
            raise RuntimeError("Renderer metadata does not match the PNG or backend")
        if any(file_hash(p) != digest for p, digest in hashes.items()):
            raise RuntimeError("Root QML/dependency changed during rendering; retry with a stable fixture")
        if args["imageMode"] == "image" and len(data) > MAX_IMAGE:
            raise ValueError("PNG exceeds 4 MiB attachment limit; use imageMode='path' and the host image-reading tool")
        metadata.update({
            "outputPath": args["outputPath"], "qmlPath": args["qmlPath"],
            "importPaths": args["importPaths"], "width": args["width"], "height": args["height"],
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "qmlSha256": hashes[args["qmlPath"]], "dependencyHashes": hashes,
            "initialProperties": args["initialProperties"], "imageMode": args["imageMode"],
            "rendererSha256": file_hash(RENDERER),
            "toolVersion": VERSION, "pythonVersion": sys.version.split()[0],
            "diagnostics": diagnostics.strip(),
        })
        records = []
        for line in diagnostics.splitlines():
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or "level" not in record:
                    raise ValueError("Invalid diagnostic")
            except ValueError:
                record = {"level": "warning", "message": line, "source": None, "line": None, "category": "unstructured"}
            records.append(record)
        metadata["diagnosticRecords"] = records
        checks = geometry_results(args["geometryChecks"], metadata.get("measurements", {}))
        metadata["geometryResults"] = checks
        failures = []
        if any(check["status"] == "FAIL" for check in checks):
            failures.append({"code": "GEOMETRY_FAILED", "message": "One or more explicit geometry rules failed",
                             "hint": "Inspect the retained PNG and measured/expected values; correct the owning layout or its declared contract"})
        if args["warningsPolicy"] == "error" and any(r["level"] in ("warning", "critical", "fatal") for r in records):
            failures.append({"code": "DIAGNOSTICS_FAILED", "message": "Strict warning policy rejected Qt/QML diagnostics",
                             "hint": "Inspect diagnosticRecords and fix the source; report policy is an explicit opt-out"})
        metadata["acceptance"] = "FAIL" if failures else "PASS"
        metadata["acceptanceErrors"] = failures
        with publication_lock:
            if cancelled.is_set():
                raise Cancelled("Render cancelled before publication")
            publish(data, parent, name)
        return metadata, data if args["imageMode"] == "image" else None
    finally:
        os.close(parent)


def send(message):
    with SEND_LOCK:
        sys.stdout.write(json.dumps(message, ensure_ascii=True, allow_nan=False) + "\n")
        sys.stdout.flush()


def error(request_id, code, message, data=None):
    details = {"code": code, "message": message}
    if data is not None:
        details["data"] = data
    send({"jsonrpc": "2.0", "id": request_id, "error": details})


def complete(result, protocol):
    if protocol == MODERN_PROTOCOL:
        return {**result, "resultType": "complete", "_meta": {
            "io.modelcontextprotocol/serverInfo": {"name": "qml-preview", "version": VERSION}}}
    return result


def failure_result(exc, protocol):
    if isinstance(exc, ToolFailure):
        code, hint = exc.code, exc.hint
    elif isinstance(exc, TimeoutError):
        code, hint = "TIMEOUT", "Check the fixture's readiness condition and bounded startup operations"
    elif isinstance(exc, FileExistsError):
        code, hint = "OUTPUT_EXISTS", "Choose a new output filename; originals are never overwritten"
    elif isinstance(exc, OSError):
        code, hint = "FILESYSTEM_ERROR", "Check renderer/files, permissions and explicit paths; output ancestors cannot be symlinks"
    elif isinstance(exc, ValueError):
        code, hint = "INPUT_ERROR", "Check the documented tool arguments, existing QML/dependencies and image mode"
    else:
        code, hint = "RENDER_ERROR", "Inspect diagnostics and the reviewed QML/imports; rebuild the renderer if needed"
    metadata = {"error": {"code": code, "message": str(exc), "hint": hint}}
    result = {"content": [{"type": "text", "text": json.dumps(metadata)}], "isError": True}
    if protocol != "2024-11-05":
        result["structuredContent"] = metadata
    return result


class Server:
    def __init__(self):
        self.protocol = None
        self.initialized = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qml-preview")
        self.calls = {}
        self.lock = threading.Lock()

    def close(self):
        with self.lock:
            for cancelled in self.calls.values():
                cancelled.set()
        self.executor.shutdown(wait=True)

    def execute(self, request_id, name, args, cancelled, protocol):
        try:
            if cancelled.is_set():
                raise Cancelled("Call cancelled before execution")
            metadata, image = healthcheck(cancelled) if name == "healthcheck" else render(args, cancelled, self.lock)
            result = {"content": [{"type": "text", "text": json.dumps(metadata)}], "isError": metadata.get("acceptance") == "FAIL"}
            if image is not None:
                result["content"].append({"type": "image", "mimeType": "image/png",
                                          "data": base64.b64encode(image).decode("ascii")})
            if protocol != "2024-11-05":
                result["structuredContent"] = metadata
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result = failure_result(exc, protocol)
        except Exception as exc:
            result = failure_result(RuntimeError(f"Internal tool error: {type(exc).__name__}"), protocol)
        finally:
            with self.lock:
                self.calls.pop(request_id, None)
        # MCP cancellation requires no result; cancellation after publication may
        # race with completion, which clients must handle as already completed.
        if not cancelled.is_set():
            send({"jsonrpc": "2.0", "id": request_id, "result": complete(result, protocol)})

    def handle(self, message):
        if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
                or not isinstance(message.get("method"), str)
                or ("id" in message and (type(message["id"]) not in (int, str)
                    or isinstance(message["id"], str) and not valid_string(message["id"], 1, 256)))):
            error(None, -32600, "Invalid JSON-RPC request")
            return
        method = message["method"]
        if "id" not in message:
            if method == "notifications/initialized" and self.protocol:
                self.initialized = True
            elif method == "notifications/cancelled":
                params = message.get("params")
                if isinstance(params, dict) and type(params.get("requestId")) in (int, str):
                    with self.lock:
                        cancelled = self.calls.get(params["requestId"])
                        if cancelled:
                            cancelled.set()
            return
        request_id = message["id"]
        params = message.get("params", {})
        try:
            if not isinstance(params, dict):
                raise InvalidParams("params must be an object")
            with self.lock:
                if request_id in self.calls:
                    raise InvalidParams("Duplicate in-flight request id")
            meta = params.get("_meta", {})
            modern = isinstance(meta, dict) and any(key in meta for key in (
                "io.modelcontextprotocol/protocolVersion", "io.modelcontextprotocol/clientCapabilities", "io.modelcontextprotocol/clientInfo"))
            protocol = self.protocol
            if modern or method == "server/discover":
                if not isinstance(meta, dict) or not valid_string(meta.get("io.modelcontextprotocol/protocolVersion"), 1, 32) or not isinstance(meta.get("io.modelcontextprotocol/clientCapabilities"), dict):
                    raise InvalidParams("Modern requests require protocolVersion and clientCapabilities in params._meta")
                requested = meta["io.modelcontextprotocol/protocolVersion"]
                if requested != MODERN_PROTOCOL:
                    error(request_id, -32022, "Unsupported protocol version", {
                        "supported": [MODERN_PROTOCOL, *reversed(PROTOCOLS)], "requested": requested})
                    return
                info = meta.get("io.modelcontextprotocol/clientInfo")
                if info is not None and (not isinstance(info, dict) or not valid_string(info.get("name"), 1, 256) or not valid_string(info.get("version"), 1, 256)):
                    raise InvalidParams("Invalid modern clientInfo")
                protocol = MODERN_PROTOCOL
            elif "_meta" in params and not isinstance(meta, dict):
                raise InvalidParams("_meta must be an object")
            params = {key: value for key, value in params.items() if key != "_meta"}
            if method == "server/discover":
                if params:
                    raise InvalidParams("server/discover takes only _meta")
                result = {"supportedVersions": [MODERN_PROTOCOL, *reversed(PROTOCOLS)], "capabilities": {"tools": {}},
                          "ttlMs": 0, "cacheScope": "private",
                          "instructions": "Render reviewed inert QML consumers, inspect PNGs, check native design/anti-slop and rerender corrections. Geometry PASS is not design acceptance."}
            elif method == "initialize" and protocol != MODERN_PROTOCOL:
                if self.protocol:
                    raise InvalidParams("Server already initialized")
                if (not isinstance(params.get("protocolVersion"), str)
                        or not isinstance(params.get("capabilities"), dict)
                        or not isinstance(params.get("clientInfo"), dict)
                        or not valid_string(params["clientInfo"].get("name"), 1, 256)
                        or not valid_string(params["clientInfo"].get("version"), 1, 256)):
                    raise InvalidParams("Missing initialization fields")
                requested = params["protocolVersion"]
                self.protocol = requested if requested in PROTOCOLS else PROTOCOLS[-1]
                result = {"protocolVersion": self.protocol, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "qml-preview", "version": VERSION},
                          "instructions": "For plugin UI changes: healthcheck, render the reviewed actual consumer with inert models, inspect its PNG in an image-capable host, review native design and anti-slop, fix authorized findings and rerender. Missing capabilities are blockers, not visual PASS. No desktop access or external viewers for development previews."}
            elif method == "ping":
                if protocol == MODERN_PROTOCOL:
                    error(request_id, -32601, "ping is not supported by modern MCP")
                    return
                if params:
                    raise InvalidParams("ping takes no parameters")
                result = {}
            elif protocol != MODERN_PROTOCOL and not self.initialized:
                raise InvalidParams("Complete initialize and notifications/initialized first")
            elif method == "tools/list":
                if params:
                    raise InvalidParams("tools/list takes no parameters")
                result = {"tools": [
                    {"name": "healthcheck", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                     "description": "Preflight the offscreen Qt renderer, versions, imports and limits without executing project QML."},
                    {"name": "render_qml", "inputSchema": SCHEMA,
                      "description": "Render the reviewed actual QML consumer after each meaningful plugin UI change and before delivery. Returns a PNG attachment by default plus geometry, hashes and diagnostics. Inspect the image, perform native design/anti-slop review, fix and rerender. NOT a sandbox; use inert models and explicit imports."}]}
                if protocol == MODERN_PROTOCOL:
                    result.update({"ttlMs": 0, "cacheScope": "private"})
            elif method == "tools/call":
                if set(params) - {"name", "arguments"}:
                    raise InvalidParams("tools/call accepts only name, arguments and _meta")
                name = params.get("name")
                if name not in ("render_qml", "healthcheck"):
                    raise InvalidParams("Unknown tool")
                args = params.get("arguments", {})
                if protocol == MODERN_PROTOCOL and not isinstance(args, dict):
                    raise InvalidParams("tools/call arguments must be an object")
                if name == "healthcheck":
                    if not isinstance(args, dict) or args:
                        raise InvalidParams("healthcheck takes no arguments")
                else:
                    try:
                        args = validate(args)
                    except InvalidParams as exc:
                        if protocol != MODERN_PROTOCOL:
                            raise
                        send({"jsonrpc": "2.0", "id": request_id, "result": complete(failure_result(exc, protocol), protocol)})
                        return
                with self.lock:
                    if request_id in self.calls:
                        raise InvalidParams("Duplicate in-flight request id")
                    if len(self.calls) >= 8:
                        raise InvalidParams("At most 8 in-flight/queued calls are allowed")
                    cancelled = threading.Event()
                    self.calls[request_id] = cancelled
                self.executor.submit(self.execute, request_id, name, args, cancelled, protocol)
                return
            else:
                error(request_id, -32601, f"Method not found: {method}")
                return
            send({"jsonrpc": "2.0", "id": request_id, "result": complete(result, protocol)})
        except InvalidParams as exc:
            error(request_id, -32602, str(exc))
        except Exception as exc:
            # Keep the stream usable, but never silently lose a request.
            error(request_id, -32603, f"Internal error: {type(exc).__name__}")


def main():
    server = Server()
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
            if not line:
                break
            if len(line) > MAX_MESSAGE:
                while not line.endswith(b"\n"):
                    line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
                    if not line:
                        break
                error(None, -32700, "Message exceeds 1 MiB")
                continue
            if not line.strip():
                continue
            try:
                message = json.loads(line.decode("utf-8"), parse_constant=reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                error(None, -32700, "Invalid JSON")
                continue
            server.handle(message)
    finally:
        server.close()


def reject_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


if __name__ == "__main__":
    main()
