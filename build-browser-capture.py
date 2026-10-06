#!/usr/bin/env python3
"""Build the optional, fixed-plugin QML bridge into a new directory outside Git."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--inert-test", action="store_true", help="Use an isolated endpoint; never connect to the production bridge")
args = parser.parse_args()
root = Path(__file__).resolve().parent
out = args.output_dir.absolute()
if not out.is_absolute() or ".." in out.parts or any(p.is_symlink() for p in [out, *out.parents]):
    parser.error("Output must be a new absolute directory without symlink ancestors")
if any((p / ".git").exists() for p in [out, *out.parents]):
    parser.error("Build outside Git")
out.mkdir(mode=0o700)
module = out / "Slovn/ChatGPTCapture"
module.mkdir(parents=True, mode=0o700)
try:
    headers = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "Qt6Quick", "Qt6Network"], text=True))
    libraries = shlex.split(subprocess.check_output(["pkg-config", "--libs", "Qt6Quick", "Qt6Network"], text=True))
    qt_version = subprocess.check_output(["pkg-config", "--modversion", "Qt6Gui"], text=True).strip()
    qt_headers = subprocess.check_output(["pkg-config", "--variable=includedir", "Qt6Gui"], text=True).strip()
    rhi_headers = Path(qt_headers) / "QtGui" / qt_version / "QtGui"
    if not (rhi_headers / "rhi/qrhi.h").is_file():
        raise RuntimeError("Matching Qt RHI development headers required for hidden capture")
    subprocess.run(["/usr/lib/qt6/moc", *headers, str(root / "browser-capture.cpp"), "-o", str(out / "browser-capture.moc")], check=True, timeout=20)
    subprocess.run(["c++", "-O2", "-Wall", "-Wextra", "-fPIC", "-shared", "-std=c++17", "-I" + str(out),
                    *(["-DQML_CAPTURE_INERT_TEST"] if args.inert_test else []),
                    "-I" + str(rhi_headers), *headers, str(root / "browser-capture.cpp"), "-o", str(module / "libchatgptcapture.so"), *libraries], check=True, timeout=90)
    (module / "qmldir").write_text("module Slovn.ChatGPTCapture\nplugin chatgptcapture\n")
except BaseException:
    # Keep failed build diagnostics/artifacts, never recursively delete a path.
    raise
print(out)
