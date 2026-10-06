#!/usr/bin/env python3
"""One bounded isolated native capture. Never talk to the production endpoint."""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import threading
import importlib.util
import sys
from smoke import png

spec = importlib.util.spec_from_file_location('hidden_capture_api', Path(__file__).resolve().parents[1]/'mcp-qml-preview.py')
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--imports', type=Path, required=True)
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--dpr', type=int, choices=(1, 2), default=1)
parser.add_argument('--rhi', action='store_true', help='Offscreen OpenGL native render path')
parser.add_argument('--negative', choices=('disable','resize'))
args = parser.parse_args()
args.evidence.mkdir(mode=0o700)
endpoint = Path(f'/run/user/{os.getuid()}/qml-preview-slovn.chatgpt-lite-hidden-test/capture.sock')
assert not endpoint.exists(), 'Refuse a preexisting test endpoint'
fixture = Path('/home/slovn/Work/omarchy-plugins/omarchy-chatgpt-lite/tests/hidden-capture.qml')
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_SCALE_FACTOR=str(args.dpr))
if args.rhi:
    env.pop('QT_QUICK_BACKEND', None)
    env['QSG_RHI_BACKEND'] = 'opengl'
log = args.evidence / 'test.log'
with log.open('w') as stream:
    # Separate copied inert fixture selects only fixed negative behavior, never a production QML path.
    if args.negative:
        copy = args.evidence/'tst_negative.qml'
        copy.write_text(fixture.read_text().replace('import "../native" as Candidate', 'import "'+(fixture.parent.parent/'native').as_uri()+'" as Candidate').replace('property string failureMode: ""','property string failureMode: "'+args.negative+'"'))
        fixture = copy
    process = subprocess.Popen(['/usr/lib/qt6/bin/qmltestrunner', '-import', str(args.imports), '-input', str(fixture)], env=env, stdout=stream, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 7
        while not endpoint.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert endpoint.exists(), 'No inert bridge; inspect test.log'
        def receive(peer, count):
            data = bytearray()
            while len(data) < count:
                block = peer.recv(count-len(data))
                assert block, 'Incomplete response'
                data.extend(block)
            return bytes(data)
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(5)
            peer.connect(str(endpoint))
            pid, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            assert pid == process.pid and uid == os.getuid(), 'Never connect to production'
        time.sleep(.05)  # Complete disconnected identity probe, no capture retries.
        api.endpoint = lambda: endpoint
        target = args.evidence/'browser.png'
        request = api.validate_capture({'pluginId':api.CAPTURE_PLUGIN_ID, 'consent':api.CAPTURE_REQUEST_CONSENT,
            'outputPath':str(target.absolute()), 'timeoutMs':5000}, api.InvalidParams)
        try:
            meta, attachment = api.capture_page(request, threading.Event(), threading.Lock(), api)
        except api.ToolFailure as exc:
            if not args.negative: raise
            assert exc.code == 'CONSUMER_CHANGED', exc.code
            process.wait(timeout=7)
            assert process.returncode == 0, log.read_text()
            assert not target.exists() and not endpoint.exists()
            (args.evidence/'negative.json').write_text(json.dumps({'case':args.negative,'code':exc.code,'no_png':True,'restored':True}))
            print('PASS: '+args.negative+' cancels hidden rendering, no PNG, restores view/focus/draft')
            sys.exit(0)
        assert not args.negative, 'Negative case unexpectedly captured'
        assert attachment is None and meta['captureMethod'] == 'QQuickRenderControl::offscreen'
        assert meta['consumerPid'] == process.pid and meta['pageKind'] == 'inert-local-fixture'
        (args.evidence/'capture.json').write_text(json.dumps(meta, indent=2))
        process.wait(timeout=7)
        assert process.returncode == 0, log.read_text()
        w, h, pixel = png(target)
        assert (w,h) == (480*args.dpr,320*args.dpr)
        assert pixel(450*args.dpr,60*args.dpr) == (0,170,68), 'Not the fresh hidden green Chromium frame'
        assert pixel(450*args.dpr,160*args.dpr) == (21,101,192)
        assert 'HIDDEN_IDENTITY_FOCUS_DRAFT_RETAINED' in log.read_text()
        assert not endpoint.exists(), 'Endpoint survived normal teardown'
        print('PASS: fresh hidden Chromium pixels, same browser/profile/renderer/draft, unmapped window and sentinel focus; inert only')
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
        # Only this isolated task endpoint, after its recorded owner has exited.
        if endpoint.exists():
            with socket.socket(socket.AF_UNIX) as check:
                check.settimeout(.1)
                try: check.connect(str(endpoint))
                except ConnectionRefusedError: endpoint.unlink()
                else: raise AssertionError('Test endpoint has a live owner; never remove')
