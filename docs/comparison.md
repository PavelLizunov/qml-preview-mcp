# Related tools and implementation review

Source review on 2026-09-30 against QML Preview MCP 0.2.0. Other tools were not
installed or executed. Descriptions below are based on the pinned source and
documentation, not independent confirmation of their runtime claims.

## Closest Qt tools

| Project | Reviewed revision | Architecture and relevant capability |
| --- | --- | --- |
| [qtPilot](https://github.com/ssss2art/qtPilot/tree/eb8bcd04907d0fdb29f69db77b7c4195ef0abbae) | `eb8bcd04907d0fdb29f69db77b7c4195ef0abbae` | Python MCP plus injected/linked C++ probe in a target Qt app; object introspection, QML geometry, accessibility and interaction |
| [qt-mcp](https://github.com/0xCarbon/qt-mcp/tree/24303a69d498417dfcec0223bfaa95964f788c17) | `24303a69d498417dfcec0223bfaa95964f788c17` | Python MCP plus in-process PySide probe; QWidget tree, screenshots, layout diagnostics and interaction |

Neither is a direct replacement for a reviewed fixture rendered in a new
offscreen process. Their running-app probes solve a broader automation problem.
GitHub search also found `danvratil/qml-mcp`, but its tree API returned an empty
repository, so it supplies no implementation to adopt. The search is not proof
that no other equivalent project exists.

qtPilot's [screenshot helper](https://github.com/ssss2art/qtPilot/blob/eb8bcd04907d0fdb29f69db77b7c4195ef0abbae/python/src/qtpilot/tools/screenshot_helper.py)
returns native MCP image content or lean file metadata. QML Preview already uses
both patterns, with explicit DPR, verified PNG dimensions and no-overwrite output.

qt-mcp's [layout inspector](https://github.com/0xCarbon/qt-mcp/blob/24303a69d498417dfcec0223bfaa95964f788c17/src/qt_mcp/probe/layout_inspector.py)
reports zero-size widgets, missing layouts, sizes below hints, text width and
overlapping siblings. These are heuristics, not a design verdict: deliberate
overlap and custom positioning can be valid. QWidget sizeHint/fontMetrics rules
must not be transplanted into Qt Quick without handling wrapping, transforms,
clipping, scroll content and intentional layering. Symmetry requires a declared
layout invariant rather than a universal assumption.

qtPilot's [QML evaluation notes](https://github.com/ssss2art/qtPilot/blob/eb8bcd04907d0fdb29f69db77b7c4195ef0abbae/docs/QML-A11Y-EVALUATION.md)
illustrate a relevant failure class: QObject parentage, QWidget discovery and
QQuickItem visual parentage are different. They also distinguish local, scene
and screen geometry. QML Preview currently searches QObject descendants for
named items and reports scene bounds. Reparented visual-only items and popup
surfaces need dedicated qualification; they are not covered by the current
fixture tests. An offscreen scene has no verified compositor position.

## Larger UI MCP references

- [Playwright MCP](https://github.com/microsoft/playwright-mcp/tree/f183dad4a52965583e3cc1d59b88cdc279e2e57d):
  accessibility snapshots, optional bounding boxes, named selectors, explicit
  image delivery modes and scale. Structural state inspection complements
  screenshots; screenshots remain necessary for visual appearance.
- [Chrome DevTools MCP design principles](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/02c0112cd57e4fa4bac31a1e69d7507601773b14/docs/design-principles.md):
  agent-agnostic APIs, compact summaries, deterministic composable tools,
  actionable errors and references for large artifacts. QML Preview's two tools
  fit the small-surface pattern, but currently duplicate full metadata as text
  and structured content and have no machine-readable error categories.
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk/tree/06d1d1e4d2106ef14a8c21d29e6cdafb39f66889):
  typed protocol handling and managed transports. Its
  [stdio implementation](https://github.com/modelcontextprotocol/python-sdk/blob/06d1d1e4d2106ef14a8c21d29e6cdafb39f66889/src/mcp/server/stdio.py)
  protects protocol streams from stray output. QML Preview isolates renderer
  stdout in a separate file, but its hand-written MCP implementation still owns
  framing, lifecycle, Unicode, cancellation and version negotiation correctness.

## Confirmed gaps and practical follow-ups

The findings below describe the pinned 0.2.0 baseline. Local 0.3.0 development
adds explicit layout assertions, visual-tree lookup/snapshots, strict warning
policy, machine-readable errors, version pairing and dual-era 2026-07-28 support.
CI is prepared for Ubuntu 22.04/24.04; hosted results require a published run.
Automatic painted-pixel clipping/occlusion and model compliance remain outside
those features. The protocol implementation still has no external runtime SDK.

1. **Protocol coverage is deliberately older than the newest specification.**
   Version 0.2.0 supports 2024-11-05, 2025-06-18 and 2025-11-25. The official
   [2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28)
   uses stateless requests and per-request negotiation. It is not supported;
   changing the advertised date alone would be incorrect. A client accepting
   2025-11-25 can use the existing negotiation; a newer-only client cannot.
2. **Measurements are data, not assertions.** There is no automatic geometry,
   alignment, symmetry, clipping or semantic-tree check. The agent or owning
   project's tests must compare expected constraints with measured objects.
3. **Render success permits nonfatal QML warnings.** Missing bindings/assets can
   produce a valid PNG with diagnostics. Agents must inspect those diagnostics;
   a future strict-warning policy needs explicit exclusions for known warnings.
4. **No hosted CI or cross-version qualification yet.** Local tests and an actual
   isolated OpenCode client passed, but no GitHub Actions or additional Qt/client
   versions have been exercised. The hand-written protocol warrants conformance
   tests, including queued admission/cancellation and framing limits.
5. **Renderer/wrapper version pairing is not enforced.** Healthcheck returns the
   renderer version and hash, but the wrapper does not reject a mismatched binary.
   Build the current renderer beside its matching wrapper before use.
6. **Workflow hooks are reminders.** They do not force a model to render or verify
   design. Direct shell edits, visual resource types not detected by the hook,
   and other clients need the owning skill/instruction workflow.

Recommended next implementation: explicit geometry assertions with a tolerance
and named objects, a bounded opt-in semantic snapshot, stricter warning/error
diagnostics, version-pair checking and hosted CI. Evaluate the official SDK
against the project's dependency-free requirement before choosing protocol
migration. Keep desktop injection, GPU/live-shell control and broad automation
outside the offscreen fixture tool's scope.

**Verdict: Extend — QML Preview MCP.** Existing Qt tools are useful references but
their in-process probes do not match this tool's actual-consumer offscreen
contract. No third-party implementation was copied for this review.
