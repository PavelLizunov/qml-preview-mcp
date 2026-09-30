# QML Preview MCP

Version 0.2.0. A local stdio MCP tool that renders reviewed Qt Quick QML fixtures
to PNG using Qt's offscreen platform and software backend. Python handles MCP;
a sibling C++ executable loads the QML and captures a completed frame.

## Build and check

Requires Linux/POSIX, Python 3.10+, a C++17 compiler, Make, pkg-config, and Qt 6
development libraries for Core, Gui, Qml and Quick. Install the QML modules and
fonts used by your fixtures separately. Tested here with Python 3.12.14,
GCC 16.2.1, Make 4.4.1 and Qt 6.11.2; other versions have not been verified.

From the project directory:

```sh
make
make check
```

The build uses `pkg-config --cflags --libs Qt6Quick`. Python has no package
dependencies. `make check` starts an owned stdio client, renders the bundled
component through its consumer fixture, validates PNG pixels, and checks failures.
Its temporary outputs are removed on exit. To retain images and provenance:

```sh
mkdir -p evidence
PYTHONDONTWRITEBYTECODE=1 python3 tests/smoke.py --evidence-dir evidence/run-1
```

The evidence directory must be new and its parent must already exist. Each run
records source/binary hashes, Qt/Python versions, effective imports, palette,
locale, logical/pixel geometry, DPR, backend and expected state in `evidence.json`.
Images start with `inspected: false`; use the host's image-reading tool to inspect
both PNGs and record the observed labels/layout before marking them inspected.
File creation and automatic pixel checks alone are not visual review.

## Launch and client configuration

Keep `mcp-qml-preview.py` and the built `qml-render` in the same directory. Both
may be moved together; neither depends on the current working directory. Launch:

```sh
python3 /absolute/path/to/qml-preview-mcp/mcp-qml-preview.py
```

The transport is one JSON-RPC object per line on stdin/stdout. Stdout contains
only protocol messages. Close stdin to stop the server. Requests execute
sequentially on one worker (at most eight calls in flight/queued); ping and
cancellation stay responsive. There is no daemon or HTTP listener. Send
`notifications/cancelled` with `requestId` to cancel a queued/active call; cancelled
requests receive no result. EOF or SIGTERM cancels owned work and exits. Render
calls have their deadline plus two seconds of startup allowance. The server
does not change file modes.

For a separately authorized OpenCode setup, merge this entry into the existing
`mcp` object, replacing the placeholder with the real path:

```json
{
  "mcp": {
    "qml-preview": {
      "type": "local",
      "command": ["python3", "/absolute/path/to/qml-preview-mcp/mcp-qml-preview.py"],
      "enabled": true,
      "timeout": 15000
    }
  }
}
```

OpenCode loads configuration at startup; a new session is needed after a config
change. Building this project does not install it or modify any client config.
The server advertises `healthcheck` and `render_qml`; a client may namespace tools differently.
Discover its actual name and schema rather than assuming a harness-specific name.
The client timeout must exceed the selected render deadline and startup allowance;
the example uses 15 seconds to cover the maximum 10-second render deadline.

## `render_qml` contract

First call `healthcheck` with `{}`. It starts Qt offscreen without executing
project QML, and reports renderer/tool/Python/Qt versions, import paths, renderer
hash, supported root types/DPR and resource limits. It does not certify that a
particular plugin's imports or assets load successfully.

| Argument | Required/default | Meaning |
| --- | --- | --- |
| `qmlPath` | Required | Absolute local path to an existing `.qml` file |
| `outputPath` | Required | Absolute path to a **new** `.png` file in an existing directory |
| `width` | 480 | Logical width, integer 1–4096 |
| `height` | 360 | Logical height, integer 1–4096 |
| `dpr` | 1 | Integer 1 or 2 |
| `importPaths` | `[]` | Up to 32 absolute project import directories, highest priority first |
| `readyProperty` | Omitted | Name of a readable boolean property on the root item |
| `timeoutMs` | 5000 | Readiness/frame deadline, integer 100–10000 ms |
| `imageMode` | `image` | PNG attachment plus metadata; `path` returns metadata only |
| `initialProperties` | `{}` | Up to 64 root properties applied before QML creation, at most 64 KiB encoded JSON |
| `locale` | Environment | Explicit Qt locale such as `ru_RU`, `en_US`, or `C` |
| `measureObjects` | `[]` | Up to 64 unique visual item `objectName` values to measure |
| `dependencyPaths` | `[]` | Up to 128 explicit absolute files hashed before/after rendering |

Unknown arguments, null top-level options, booleans in integer fields, fractional values,
relative paths and `..` path segments are rejected. Paths are at most 4096
characters; readiness property names at most 128. At most 16,000,000 physical
pixels may be requested: `width * height * dpr * dpr`.

Example `tools/call` parameters (replace paths, properties and object names with the consumer's contract):

```json
{
  "name": "render_qml",
  "arguments": {
    "qmlPath": "/absolute/path/to/project/tests/preview.qml",
    "outputPath": "/absolute/path/to/project/evidence/screen-dpr2.png",
    "width": 480,
    "height": 300,
    "dpr": 2,
    "importPaths": ["/absolute/path/to/project/qml-imports"],
    "readyProperty": "previewReady",
    "timeoutMs": 5000,
    "imageMode": "image",
    "locale": "ru_RU",
    "initialProperties": {"previewState": "error"},
    "measureObjects": ["panel", "navigation"],
    "dependencyPaths": ["/absolute/path/to/project/Panel.qml"]
  }
}
```

### Readiness and geometry

The root must derive from `QQuickItem`, such as `Item` or `Rectangle`.
`QQuickView::SizeRootObjectToView` sizes that root to the requested logical
geometry. To inspect a component's natural sizing, load it inside a fixture
`Item` that preserves its sizing bindings instead of using that component as the
resized root.

When `readyProperty` is supplied, a bounded timer observes its boolean value,
requests a frame after it becomes true, and captures after a completed frame
while the property is still true. The fixture owns the meaning of readiness
(for example, all required images/models have loaded and animations are stopped).
The renderer does not infer that meaning from an arbitrary delay.

`initialProperties` are JSON values, not code/functions. Property names must exist
and be writable on the root; type conversion/load diagnostics must be reviewed.
Qt locale changes formatting; it does not load a translation catalog. Select
project catalog/theme/model data explicitly in the reviewed fixture.

`measureObjects` requires exactly one `QQuickItem` per name. Results contain
axis-aligned logical scene bounds, implicit size, visibility, enabled/clip and
active-focus flags. They are snapshots, not a transition or compositor test.

Without `readyProperty`, `readiness` is `loaded-frame`: the QML root exists and
a frame has rendered. This does not prove asynchronous resources are ready.
With the property, `readiness` is `property-and-frame`.

DPR changes rendering density while preserving logical geometry. A 480×300
fixture at DPR 2 must produce 960×600 pixels. The image is drawn at that density,
not resized from a lower-resolution PNG. Qt encodes the PNG, then decodes it to
verify dimensions; Python checks its PNG header against the request and metadata.
Empty images, wrong DPR/geometry and PNGs over 64 MiB are errors.

### Imports, output and evidence

Qt's resource/system imports are discovered by Qt. Project paths are explicit;
`QML_IMPORT_PATH` and `QML2_IMPORT_PATH` are cleared, and the renderer's executable
directory is removed from implicit imports. There are no built-in Omarchy paths,
global project copies or temporary mocks. Input/import symlinks are canonicalized
and returned in metadata, so review their targets as part of the fixture.

Output paths reject symlinks in every ancestor and at the destination, including
dangling symlinks. The parent is pinned with a directory descriptor. PNGs are
rendered into an inherited anonymous temporary file, verified, then published
via a private temporary file and an exclusive hard link in the destination
directory. A late collision also fails without replacing the original. The
destination filesystem must support hard links. New PNGs have mode `0600`.

Success returns `isError: false` and JSON text metadata containing:

- canonical QML/project import paths and effective Qt import paths;
- logical width/height, verified pixel dimensions, actual DPR and output path;
- `backend: software`, `platform: offscreen`, Qt/Python/tool versions;
- locale, default font, capture timestamp, readiness mode/property;
- PNG size/hash, root QML hash and bounded QML diagnostics;
- renderer hash, initial properties, measured objects and explicit dependency hashes.

The root and `dependencyPaths` hashes are checked before and after rendering
(at most 16 MiB per file). They do not automatically identify the whole
import/resource tree. Record relevant dependencies, adapters,
models and locales in the owning project's evidence manifest, and keep them
unchanged during capture. Palette and UI state are fixture-owned, not inferred
by the generic renderer.

By default the result includes a PNG `image` content block and JSON metadata.
The attachment is the exact saved PNG, not a downscaled substitute. PNGs over
4 MiB require `imageMode: path`; attachment-limit errors do not publish an image.
Inspect attachments in an image-capable host, or read the returned path with its
image-reading tool. Path-only output is not an image attachment or visual review.
The active OpenCode model must declare image input in its `modalities.input`;
`attachment: true` alone does not establish image support. A text-only model
receives an unsupported-image message instead of visual evidence. Do not modify
provider settings automatically; report the missing image-capable review route.
MCP 2025-06-18 and 2025-11-25 additionally get the metadata in `structuredContent`;
2024-11-05 gets JSON text only. An unsupported requested version receives
2025-11-25, which the client must accept or disconnect.

### Errors

Malformed JSON: `-32700`. Invalid JSON-RPC request: `-32600`. Unknown method:
`-32601`. Invalid arguments/tool or incomplete initialization: `-32602`.
Unexpected server failure: `-32603`. Valid notifications never render or get replies.
Messages larger than 1 MiB are rejected, then the stream can accept another
request. Initialize, send `notifications/initialized`, then list/call tools.

QML load/import/root/readiness failures, missing renderer, invalid filesystem
destinations, permissions, timeout, collisions and image verification failures
return a tool result with `isError: true` and diagnostic text. They do not publish
a candidate image. Nonfatal Qt/QML diagnostics are returned on success and need
review; success does not certify that the QML has no binding warnings.

## Safe consumer fixtures and limits

Only run reviewed, trusted local QML and imports. Offscreen rendering is **not a
sandbox**: startup handlers, native plugins, filesystem/network APIs and subprocess
helpers still run with the user's permissions. Review them before execution.
Use inert models for mutation, commands, device access and network operations.
The wrapper owns a process group for each invocation and terminates it at the end;
helpers that deliberately escape that group are outside this guarantee.

The bundled `tests/fixture.qml` loads the actual `FixturePanel.qml` component with
an inert `QtObject` model and an explicit `FixturePalette` import. It verifies
this tool's component-consumer path. It does not certify any Home Organizer or
Omarchy plugin screen.

`Window`, `ApplicationWindow`, Quickshell shell/panel roots and host-specific
services require a reviewed project adapter presenting a `QQuickItem` consumer.
The renderer does not start Quickshell or provide host services. Software Qt
cannot verify ShaderEffect, custom GPU rendering or other unsupported visual
features; they can be omitted by Qt without a fatal load error. Read Qt's
[software adaptation limits](https://doc.qt.io/qt-6/qtquick-visualcanvas-adaptations-software.html).

There is no click/key interaction API. Fixture rendering does not establish
live-shell placement/focus, monitor hotplug, compositor behavior, accessibility
consumer behavior or correctness of real mutations. Connecting this version to
the actual OpenCode client requires a client acceptance test; the smoke client
only verifies stdio protocol behavior. No independent review has been performed.

## Agent visual-development integration

The existing [omarchy-plugin-patterns visual cycle](https://github.com/PavelLizunov/omarchy-plugin-patterns/blob/main/references/qml-visual-cycle.md) owns the required QML visual cycle,
native design and image-review procedures. For UI/state/copy changes, agents
preflight MCP, render the reviewed actual consumer after coherent edits, inspect
the PNG, review native design and anti-slop, fix authorized findings and rerender.
Before delivery, dependency hashes must match. Backend-only/doc/read-only work
retains its scope; missing tools/imports/safe fixtures are concrete blockers.

`integrations/opencode-visual-cycle.mjs` provides scoped reminders in OpenCode
after UI-related edits, in system context and during compaction. It activates
for a manifest with plugin kinds/entryPoints or when an owning skill is loaded.
It never runs QML, dispatches agents, changes permissions, or blocks unrelated
backend edits. Test its behavior with:

```sh
node tests/hooks.mjs
```

The actual OpenCode client can be tested without model inference:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/client.py --evidence-dir evidence/client-1
```

This launches an isolated OpenCode process with temporary config/data and a
local scripted HTTP fixture bound to an ephemeral loopback port. It checks real
MCP discovery/calls, image delivery, tool errors and hooks. It does not contact
a model provider or exercise the active user's session. The owned fixture stops
before exit. OpenCode may prepare its own temporary runtime dependencies during
startup; the test does not install anything into this project or global config.

For separately authorized installation, add the module by absolute `file://` URL
to OpenCode's `plugin` list and the required visual rule to its global instruction
file. Restart OpenCode yourself after configuration/skill changes. The hook is
a reminder, not an enforcement of image understanding or design quality: direct
shell edits, nested plugin folders without skill loading and other clients can
fall outside its detection. Skills/instructions carry the broader workflow.
Keep desktop access out of development evidence; use PNG attachments/harness
reading only. Native host/project design overrides web anti-slop defaults.

## Related tools and current gaps

See [the pinned source comparison](docs/comparison.md) for qtPilot, qt-mcp,
Playwright MCP, Chrome DevTools MCP and the official SDK. Version 0.2.0 has
measurements rather than automatic geometry/symmetry assertions, no hosted CI,
and no support for the newer MCP 2026-07-28 stateless protocol. The documented
2025-11-25 and older negotiation remains the supported interface.

## Source provenance and license

This local implementation extends the previously installed Python/Qt renderer
under the owner's approved development scope. It leaves that installation intact.
Baseline source SHA-256 values:

```text
mcp-qml-preview.py  6d1ee27e5b84f7540c055e2b0561bc726cbc3a67652048dd5267743beee1640c
qml-render.cpp     71036ff755956be99c4d450b9e44d5cab5a7f31a820c7aa48f444bec173df2f0
```

This project's original code and documentation are licensed under [MIT](LICENSE).
Qt and linked third-party software retain their own licensing terms. The local
development handoff and generated evidence are excluded from the source repository.
