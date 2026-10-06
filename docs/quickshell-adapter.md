# Optional Quickshell static-module adapter

The stock renderer cannot import static Quickshell plugins embedded in the shell
executable. This optional build links the same reviewed static modules and their
resource registrations into the existing renderer. It does not invoke Quickshell
main/launch, start its IPC server, launch another shell, connect to Wayland or
capture the desktop. Quickshell/Qt remain under their own licenses.

Verdict: **Extend** the native renderer. Keep default `make` portable and unchanged.
Adapter interfaces are source/version-specific; tested against Quickshell0.3.1 and
Qt6.11.2. Do not link unreviewed downloads or claim arbitrary release compatibility.

## Build

First build a reviewed Quickshell tree with its native CMake/Ninja workflow. The
adapter reuses that owning build's static-plugin objects, resources and link graph:

```sh
python3 build-quickshell-adapter.py \
  --source /absolute/reviewed/quickshell-source \
  --build /absolute/reviewed/quickshell-build \
  --output /absolute/new/qml-render-with-quickshell
```

Output must not already exist. The script does not execute the shell binary.
Review the source/build identity, native initialization and command before linking.
Back up the ordinary renderer outside Git before applying the new binary as the
sibling `qml-render`. Run `make check`, then the actual active MCP healthcheck;
`quickshellModules: true` identifies this optional build. `make` can rebuild the
ordinary renderer without this adapter. No new MCP schema or provider configuration.

## Consumer contract

The adapter creates a real Quickshell EngineGeneration/qs URL resolver, uses the
reviewed import root containing shell.qml/Commons/qmldir, registers the actual
WaylandPanelInterface on offscreen QPA and orders generation cleanup. It omits the
Wayland/X11/window-system initializer objects that would hook production platforms.
It clears WAYLAND_DISPLAY/HYPRLAND_INSTANCE_SIGNATURE inside the isolated render
process before native-module initialization. No live Hyprland connection is made.

A QQuickItem-root fixture must load the actual candidate, provide inert I/O,
keep its native surface unshown and present its actual contentItem on the capture
canvas. The fixture may reparent this exact subtree; it must not reconstruct an
approximate panel. Explicit readiness, geometry, dependency hashes, PNG inspection
and warning review remain required. Offscreen is not a sandbox: Process/FileView
and site I/O still require fixture admission controls.

Healthcheck does not execute QML. Render metadata adds hostAdapter; software/offscreen
and interaction:false remain unchanged. Compositor geometry/focus/lock/grab, separate
auxiliary windows and GPU rendering are NOT verified. Quickshell's missing-Hyprland
warning is expected evidence of absent connection, not a native-compositor PASS.
Strict warningsPolicy:error still rejects warnings; do not suppress them globally.

## Observed local evidence

Default build:24 smoke groups and9 version0.3 groups PASS after source changes.
Applied adapter:the same groups PASS. Actual ChatGPT native wrapper imports successfully,
inert browser/input render captured, hide/show synthetic draft retention checked,
owned-profile whole-Loader removal exits cleanly. Evidence remains outside Git
in the owning plugin's task directory. A fixture initially tried mapping/reparenting
an offscreen layer during retention and segfaulted; keeping the fixture layer unshown
removed that path. No production-shell conclusion follows from that renderer failure.

Source/API differences require rebuilding and repeating these checks. No hosted CI
run, publication, global skill changes or cache/model experiment was performed.
