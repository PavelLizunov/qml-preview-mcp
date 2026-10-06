#!/usr/bin/env python3
"""Link renderer to a previously reviewed and fully built Quickshell tree."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--build', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source, build, output = args.source.resolve(strict=True), args.build.resolve(strict=True), args.output.absolute()
if output.exists() or output.is_symlink():
    sys.exit('Output already exists; preserve the previous renderer')
root = Path(__file__).resolve().parent
# Reuse the owning build's resolved static plugin/resource/link dependency graph,
# not guessed Quickshell module lists or a different installed host executable.
commands = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands', 'quickshell'], text=True)
link = shlex.split(commands.splitlines()[-1])
objects, libraries = [], []
for token in link:
    if token.endswith('.o'):
        if token.startswith(('src/CMakeFiles/quickshell.dir/', 'src/wayland/CMakeFiles/quickshell-wayland-init.',
                             'src/x11/CMakeFiles/quickshell-x11-init.', 'src/wayland/windowmanager/CMakeFiles/quickshell-wayland-windowsystem-init.')):
            continue
        objects.append(str(build / token))
    elif token.endswith('.a') or '.so' in token:
        libraries.append(token if token.startswith('/') else str(build / token))
    elif token.startswith('-l'):
        libraries.append(token)
if not objects or not libraries:
    sys.exit('Missing resolved Quickshell plugin/link inputs')
qt = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Quick', 'Qt6Widgets', 'Qt6WaylandClient'], text=True))
command = ['c++', '-O2', '-fPIC', '-std=c++20', '-DQML_PREVIEW_QUICKSHELL', '-I' + str(source / 'src'),
           str(root / 'qml-render.cpp'), *qt, *objects, '-Wl,--start-group', *libraries, '-Wl,--end-group', '-o', str(output)]
try:
    subprocess.run(command, check=True, timeout=90)
except (subprocess.SubprocessError, OSError):
    output.unlink(missing_ok=True)
    raise
print(output)
