# Browser-content capture contract and acceptance plan

## Image-review scope correction

The previous unconditional ban on giving account PNGs to any model/provider was
an incorrect interpretation, not a native capture security requirement. The tool
still saves a private local PNG outside Git and returns metadata/path only; it
never automatically attaches image bytes. The requesting assistant may use the
host image reader when the user authorizes visual review of that account-capable
image. Onward sharing with other models/services follows the user's actual
restrictions. Local-capture-only consent is not automatically image-review consent,
and an explicit no-transfer instruction remains binding. Do not impose a broader
ban than the user requested. Historical no-transmission evidence below remains
accurate, but is not a standing prohibition. Closed capture admission, output
permissions, fixed primary target and no-input/no-navigation invariants remain.


## Hidden capture extension — installed bridge, live page coverage pending

Verdict: Extend the fixed native bridge with QQuickRenderControl, not another
browser/profile or desktop automation. The sections below retain earlier
visible-only implementation history; their hidden refusal does not describe the
new candidate. Source capture_plugin_page keeps its closed consent/schema and
path-only privacy, but additionally validates QQuickRenderControl::offscreen.
The current MCP catalog advertises the new method. First real hidden production
capture returned CONSUMER_UNAVAILABLE despite HIDDEN/SUCCEEDED primary1; the view
appears detached from its native window on hide. Windowless native capture remains
unresolved. No PNG or production hidden PASS is claimed.

Qt item grab requires a visible effective window. The hidden branch instead
creates one non-platform QQuickWindow with QQuickRenderControl and a bounded
software paint device or RHI render texture. It temporarily visually reparents
only the explicit existing primary browser, never QObject/profile ownership,
then restores its parent/position/size. No show/create platform-window, focus
request, input, navigation, account JS, DOM, storage or second browser is used.
A hidden loaded Active view is required; no forced lifecycle resume/discard.
Ten40ms frames and one readback provide a finite paint allowance, not page-settled
proof. Focus/window visibility/renderer/size/loading changes refuse publication.
Disable/disconnect/destruction restore the item and release graphics resources.
No background renderer/timer persists after the request.

Self-reviewed changes: browser-capture.cpp, hidden-browser-render.hpp,
mcp-qml-preview.py, build-browser-capture.py and tests/hidden_capture.py;
plugin tests/hidden-capture.qml uses only off-record inert HTML. No independent
review or OS sandbox claimed. Same-UID trust and cached-QML provenance limits
remain. Matching installed Qt RHI development headers are a new build requirement;
this uses the versioned RHI API and needs rebuild/retest on Qt changes.

Three final positive actual-Browser cases pass: software DPR1, OpenGL DPR1 and
software DPR2. Each proves fresh green Chromium pixels after a synthetic DOM
change, same browser/profile/renderProcessPid/draft, no visible test window,
unchanged unrelated input focus, restored parenting and endpoint teardown.
All three PNGs were inspected with the harness: green fresh-frame label, blue
Chromium label, retained input on white. They are not ChatGPT account coverage.
Two finite negative cases disable/resize return CONSUMER_CHANGED with no PNG,
retaining draft/focus/parent. Existing make check24smoke+9v03groups passes.
Initial feasibility cases failed zero-sized hidden fixture, software-adaptation
selection and root geometry; four refusals, then corrected software/OpenGL PASS.
Failed owned tester cleanup sent SIGTERM; not an unexplained production crash.
Budget:6feasibility renders/3builds, followed by declared3final cases/1build,
2cancel negatives,1production packaging build;11inert runs/5builds total,
no retries until PASS or live/account capture. Evidence and reviewed ready module:
/home/slovn/.local/share/qml-hidden-capture-1isd7hdn/{acceptance.json,budget.json,
ready-native-capture-module}. No fixture becomes evidence of the real website.

Activation completed after user reaffirmed explicit same-task ChatGPT draft-loss
waiver. Earlier block was an approval-continuity error, not a fresh critical risk.
One verified managed stop/start changed host485965 to601748; only two module files
were applied while stopped, with backup hidden-capture-76z4wzcr. New binary hash
84e73747610e5ee58d420df6ae66652691100e4ae5f9724ce3f1a9207af480cd matches
checked candidate and mapped path, bridge peer PID/UID match, no-consent request
ADMISSION_DENIED with no PNG. Shell ping/bar27x26 and Discord ready recovered.
No account capture, popup opening or input during application. Current primary
STOPPED after restart: hidden capture requires an existing page, never creates
one. Fresh native MCP catalog advertises new hidden behavior; active chat wrapper
still needs a safe reload/fresh client for changed method validation. No forced
MCP termination in the current session. Wayland production/fractional-DPR/physical
focus and concurrent physical popup-open remain unverified. Visual image review
requires the user's scope; capture does not grant menu automation or interaction
acceptance. The task-owned waiver never applies to unrelated plugin drafts.
Local deployment evidence: qml-hidden-capture-1isd7hdn/deployment.json.

Reproduce only in isolation (distinct compiled test socket never production):

```sh
python3 build-browser-capture.py --inert-test --output-dir /absolute/new/build
python3 tests/hidden_capture.py --imports /absolute/new/build --evidence /absolute/new/evidence
# Also --rhi, --dpr 2, or --negative disable / --negative resize, each new output.
```


Verdict: **Extend** the existing renderer with an optional, plugin-owned native
capture bridge. Do not add a shell, standalone browser, DevTools endpoint, input
API, page script evaluator, profile copier or desktop screenshot facility.

## Invariants and finite test budget

Preserve the dirty starting tree, existing healthcheck/render_qml contracts and
production browser/profile lifetime. A direct human request for a local image of
this specific current page is sufficient consent for that image; do not repeat
confirmation. A request to implement/review the bridge alone is not account-image
consent. This correction task performs no authenticated capture.
Outputs are private local files outside Git; capture returns a path. Image
inspection or onward sharing follows the user's authorized scope. Hidden surfaces must fail,
not be opened, moved or reparented by the bridge.

Budget for this task, with no automatic retries: one baseline and one final
existing regression-suite run (180 seconds each); at most six deterministic
actual-Browser offscreen capture attempts (10 seconds each); at most 60 bounded
local protocol/admission negative cases; three native build attempts (90 seconds
each); at most three public capability research calls; no live-site navigation,
account capture, message submission or production popup state change. Corrected
snapshots may use the remaining budget, never retry until PASS.

Acceptance checks: preserve old regressions; discover the new separate tool;
validate closed arguments and consent before connecting; pin a symlink-free output
directory, reject Git destinations and collisions; verify bridge peer UID and
consumer identity; bound request/response size, time, single-flight capture and
late callbacks; refuse disabled, hidden, loading, missing/changed consumer and
wrong targets; retain hash/timestamp/DPR/method provenance without URLs, DOM,
storage, drafts or diagnostics containing page data. Inspect every evidence PNG.
Separate pixel capture, inspection, geometry, interaction and live-site coverage.

## Native research and installed-host evidence

Qt WebEngine uses Qt Quick scene-graph nodes for Chromium's composed frames:
https://wiki.qt.io/QtWebEngine/Rendering . ItemGrabResult is an in-memory subtree
image, not a filesystem/browser automation API:
https://doc.qt.io/qt-6/qml-qtquick-itemgrabresult.html . The installed Qt 6.11.2
WebEngineView header has no public screenshot method; inherited grabToImage must
be demonstrated rather than presumed to capture Chromium correctly.

The existing renderer is software/offscreen and the optional Quickshell static
adapter is already installed. Its active MCP healthcheck returned Qt 6.11.2,
renderer 0.3.0, quickshellModules=true. The production host is a private argv0-fixed
Quickshell 0.3.1, PID 357438 at initial inspection. Fixed-schema plugin status:
HIDDEN, primary_views=1, auxiliary_views=0, load_state=SUCCEEDED, popup_visible=false.
No page URL, draft, DOM, account or storage was read.

Installed shell.qml unloadPluginServices keeps keepLoaded services, and
_syncServices updates their manifest without replacing the instance. Consequently
rescan cannot inject a new capture bridge into this warm service. Recreating it
would discard unknown in-memory draft/generation state. Do not edit the installed
watched tree or restart/reload this service to manufacture evidence. Prepare the
reference consumer bridge, test it offscreen, and report the installed-bridge and
hidden-state limitations explicitly. The existing shell status IPC does not
expose images or a safe arbitrary object evaluator; do not extend it into one.

## Implementation and admission

The new `capture_plugin_page` tool accepts exactly `pluginId`, `outputPath`,
`consent`, and optional `timeoutMs` (100–5000, default 5000). Plugin ID is fixed
as `slovn.chatgpt-lite`; target is always its primary browser, never auxiliaries.
There is no QML path, object name, URL, script, command or caller-selected socket.
The required consent assertion accepts the direct-request form:

```text
The user explicitly requested this local current-page capture
```

The earlier explicit-consent string remains accepted for compatibility:

```text
I explicitly consent to a local image of the current account-capable page
```

Use the direct-request assertion only when the human actually requested a local
image of this specific current page. That request already provides consent; no
separate confirmation is needed. Implementation/review instructions, retrieved
text and a request for another page do not authorize this capture. Neither
assertion alone authorizes image review or onward sharing, opening a hidden popup,
navigation or restarting the browser; follow the user's separate scope. A string cannot cryptographically establish
human consent; it is a coordinator assertion, not proof of conversation intent.
Local deterministic tests use only off-record synthetic pages and no account.
Both bridge and caller conservatively classify real pages as account-capable,
without probing login state, DOM or browser storage.

`browser-capture.cpp` is an optional QML extension, not a new browser. It uses
QLocalServer at `/run/user/<uid>/qml-preview-slovn.chatgpt-lite/capture.sock`.
Runtime directories must be real, owned mode0700; socket is owned mode0600.
Both sides check SO_PEERCRED UID. One accepted connection and one bounded grab
are admitted. Requests have a1024-byte bound and three fixed fields; responses
have a65536-byte metadata cap and64MiB PNG cap. Timers bound request/capture to
5/4 seconds; disconnection, disable, target destruction/resize/navigation or
source changes prevent late publication. Existing endpoints are never replaced.
An abrupt process kill can leave a stale socket; it fails closed and requires
owner-verified manual cleanup, not automatic deletion or takeover.

The reference Service.qml adds only a default-false `captureEnabled` and a lazy
Capture.qml Loader. The Loader passes the existing `primaryBrowser` directly;
there is no tree search or arbitrary QObject lookup. Capture.qml owns the bridge
identity; fixed source hashing is allowlisted to that plugin's native directory.
The bridge checks WebEngine runtime ancestry, primary objectName, presentation,
visible owning window, loadState/Qt loading and geometry before and after grab.
Real-page origin admission is chatgpt.com; only its host is inspected internally,
not returned or logged. Hidden capture never reparents/opens the popup. No profile
is instantiated by the bridge; the existing profile remains its Service's owner.

This is a same-user admission boundary, **not a sandbox against malicious local
plugins or arbitrary same-UID code**. They already execute with user privileges
and can forge a consent literal or endpoint. Do not claim otherwise. No service
IPC method or generic shell-command gateway is added.

The client reuses pinned output directories/exclusive0600 publication, rejects
Git ancestors and symlinks, verifies peer PID/metadata/PNG dimensions/DPR and
fixed source hashes, and returns text provenance only. There are no image content
blocks. Account PNGs may be inspected through the host image reader when user
scope permits visual review; do not forward them to other routes outside that scope.
The harness image inspection in this task used only synthetic off-record pages.

## Optional build and reference integration

Requires the existing Qt6 Quick development packages plus Qt6 Network and moc.
The portable renderer and its Makefile are not changed by this optional build.
Build once into a new directory outside Git:

```sh
python3 build-browser-capture.py --output-dir /absolute/new/local-capture-imports
```

The script prints the import root with Slovn/ChatGPTCapture/qmldir and
libchatgptcapture.so. Supply that reviewed root in render_qml importPaths for
local tests. Only explicitly enabling the reference Service's captureEnabled
creates the endpoint. Production integration additionally needs the reviewed
QML import root made available to the existing host and an explicit opt-in on
the owning Service. No installer, environment rewrite, live manifest edit,
rescan, enablement or restart is performed by this task. Recreating the warm
service without checking unknown unsaved work is not an acceptable setup step.

Local pixel test (exact fixed reference consumer, not an installed/account claim):

```sh
python3 tests/capture.py \
  --consumer /home/slovn/Work/omarchy-plugins/omarchy-chatgpt-lite/tests/capture-preview.qml \
  --imports /absolute/local-capture-imports \
  --evidence-dir /absolute/new/local-evidence
```

The test uses the existing renderer, actual candidate Browser.qml and an
explicitly off-record memory-cache profile. Synthetic HTML is loaded once before
the request; capture never replaces it, navigates, opens a browser or executes
JavaScript. Metadata explicitly says `pageKind: inert-local-fixture`. Pixel/CRC
checks and image inspection must demonstrate Chromium composition. This does
not establish the ChatGPT interface, production GPU composition or login.

## Provenance and coverage limitations

Results include capture kind/method, logical/pixel dimensions, fractional DPR,
UTC timestamp, fixed consumer ID/target, SO_PEERCRED PID/UID, Qt version, local PNG
path/size/SHA256, wrapper hash and available fixed current source hashes.
Current on-disk hashes do **not** attest the loaded revision of a warm QML cache.
Bridge binary, host imports and GPU dependencies are not fully identified by this
first extension; record their available hashes separately in the local manifest.
There is no invented full dependency or production readiness claim.

Readiness is `navigation-succeeded-and-item-grab; page-settled-unknown`, with
pageSettled:null. A bounded paint allowance in the local test is not a settled-page
oracle. The PNG remains imageInspected:false until a separate recorded review.
Geometry coverage is dimensions-only. Interaction/liveSiteVerified are false;
menus, auxiliary windows, file/permission dialogs, scroll/selection, active
conversation/generation, responsive states and network completion are untested.
Visible current production capture remains unverified until bridge safely loads,
a direct current-page image request or explicit account-image consent exists
and a capture is actually performed.

## Direct-request consent correction — 2026-10-06

The caller contract accepts a direct user request for this specific local
current-page PNG as consent, without a second confirmation. Missing/false/generic
implementation assertions still fail before connection. The older explicit
consent literal remains compatible; native peer wire protocol is unchanged.
A caller assertion cannot prove intent or protect against malicious same-UID code.
No image attachment/model transfer, hidden-page opening, navigation, browser
restart or profile changes were added.

Frozen old validator rejected the new direct-request assertion (red); changed
validator accepts it (green). Fresh stdio discovery and admission negatives pass;
make check passed24smoke and9v03groups. One actual off-record candidate Browser
run passed Chromium pixel checks, five native admission refusals and teardown.
The inspected480x320PNG contains labeled inert blocks, not the ChatGPT account.
No live account capture or production consumer mutation occurred. Native bridge
binary and renderer were reused unchanged, not rebuilt. Evidence is outside Git:
~/.local/share/qml-capture-consent-fix-fawe08os/.

The already-loaded chat MCP still advertises the old consent schema; fresh
clients load the corrected source. Healthcheck succeeded but does not refresh
that catalog or attest the bridge in a running browser. No forced reconnect,
production browser restart or fabricated authenticated acceptance is claimed.

## Observed checks

Baseline make check:24 smoke groups and9 v03 groups passed. Active MCP
healthcheck passed before changes; fresh stdio discovery advertises the new tool.
The installed watched consumer tree was never edited by this task. Later status
showed host PID415621 rather than initial357438, and new installed controls;
these were concurrent external changes, not caused or overwritten by this task.
The page stayed HIDDEN/SUCCEEDED with one primary view and zero auxiliaries.

Native build attempt1 failed at moc include resolution. The corrected include
flags built attempt2. First actual capture refused CONSUMER_UNAVAILABLE because
qmlContext(view) is the instantiation context, not Browser.qml. The owning
Capture.qml identity replaced that false assumption; attempt3 built successfully.
A refused test socket left by cancellation was checked inactive (connection
refused) and only that exact task-owned socket was removed. No live socket was
replaced. These are recorded failures, not first-pass success.

The subsequent local capture succeeded:480x320,DPR1,Qt6.11.2, exact candidate
Browser Chromium subtree. Both browser.png and wrapper.png were inspected:
magenta upper block with CHROMIUM PRIMARY PIXELS, blue block with Local
off-record page, not ChatGPT, white lower text. The PNGs are identical, show real
Chromium text/CSS pixels and are not a blank rectangle. This demonstrates the
native item capture on this actual local Browser consumer only.

Evidence is local, outside Git:
`/home/slovn/.local/share/qml-preview-capture/task-97mtinzz/pixels-3/`.
Authenticated-site capture was not performed. Installed-bridge probe returned
BRIDGE_UNAVAILABLE before any page access. Do not substitute an unauthenticated
ChatGPT page or this synthetic HTML for authenticated coverage.

Final make check passed all24 smoke and9 v03 groups again. Only the smoke catalog
assertion was expanded for the new tool; existing render/admission/regression
expectations were retained. The standalone wrapper/binary relocation check still
passes: capture client code lives in the wrapper, not a new mandatory sibling.
The ordinary renderer binary and all pre-existing adapter source/untracked files
match their initial SHA256 exactly. git diff --check and Python AST parsing pass.

Actual hidden and disabled native consumer checks returned HIDDEN_UNSUPPORTED
and BRIDGE_UNAVAILABLE respectively, without a browser PNG. Both renderer output
PNGs were inspected: hidden canvas is blank (not claimed as browser evidence);
disabled bridge still renders the local Chromium page normally. Endpoint teardown
passed on successful native runs. Final DPR1 capture checks CRC and exact magenta,
blue and white pixels; final browser/wrapper PNGs were both inspected and are
identical. The evidence manifest records source/binary hashes and inspections:
`/home/slovn/.local/share/qml-preview-capture/task-97mtinzz/acceptance.json`.

The sixth/final actual-consumer attempt at DPR2 included direct native admission
negatives. Empty request was refused. Malformed JSON was also refused, but the
test incorrectly expected BAD_REQUEST rather than the actual ADMISSION_DENIED;
the assertion stopped that run before its PNG capture. The expectation was
corrected and test teardown now explicitly cancels the renderer on assertion
failure. No seventh render was run: DPR2 bridge capture and remaining direct
native negative cases remain NOT VERIFIED. No image is claimed from this failed
run. Existing fixture renderer DPR2 coverage still passes, but is not bridge DPR2
coverage. QML lint with the bridge import root still reports BrowserCapture
unresolved because this dynamic extension lacks generated qmltypes; runtime
import/build success does not make that lint warning disappear.

Budget accounting: three native build attempts and six actual capture-consumer
renders were used, with no request retries or live-site requests. Re-running the
same deterministic protocol-negative prefix for multiple consumer states exceeded
the original60-local-case execution ceiling; the script lacked a shared counter.
This is a verification-budget deviation, not a clean budget PASS. Future runs
should execute the admission suite once and separate native state probes, or use
an externally counted aggregate budget. No model/provider requests or account
images were involved. The correction was not used to justify additional renders.

## Direct security/acceptance self-review

Reviewed only task-owned wrapper/bridge/build/test/doc changes and the reference
Service capture Loader. Existing version pairing, renderer subprocess ownership,
output descriptor publication and inert fixture semantics remain intact. New
trust flow is MCP closed consent/schema -> private fixed Unix peer -> existing
primary WebEngine pointer -> bounded item PNG -> checked local0600 publication.
No cookies, credentials, storage, DOM, draft/history export, request interception,
JavaScript evaluator, input/command API or desktop/window capture was introduced.
Raw page URLs and console messages are not reflected into MCP results.

Residual limits: consent is caller asserted; same-UID malicious code is outside
this boundary. A same-user directory rename/socket substitution is not isolated
by an OS sandbox; current source hashes do not attest loaded cached QML. Extreme
native PNG encoding/hashing latency and rare timeout/destroy/navigation races
were source-reviewed, not exhaustively exercised in the actual Qt host. An
abrupt renderer kill can leave an inert socket. GPU/fractional-DPR production
pixels, final DPR2 bridge capture, native auxiliary/menu/dialog interactions and
complete native admission matrix remain unverified. Direct review is not
independent signoff. Overall installed authenticated acceptance is **blocked**,
not production-ready; local DPR1 Chromium pixel capture is demonstrated.

## Installed activation after user clarification

The user waived draft retention as a deployment blocker. Installation proceeded
without another routine approval; account capture was not part of activation.
The reviewed native module was copied inside the installed plugin as
`native/capture-module`; Capture.qml uses its relative directory import, with no
global import/environment changes. Existing expanded controls, Content, Browser,
Theme and bar placement were preserved. Service's existing captureEnabled Loader
was enabled locally. The reference candidate remains default-off.

Two warm-host activation approaches failed: the existing widget stayed cached;
a fresh widget URL was rejected with File name case mismatch and temporarily
removed the trigger. Original manifest/widget routing was restored exactly.
After checking lock idle, organizer closed/not busy, no recorder processes and
only background/bar/rail surfaces, one supported managed-host restart loaded
the existing Service Loader successfully. No compositor/session restart or second
Quickshell instance was used. Current host PID474160 owns the private bridge;
SO_PEERCRED matched PID/UID. An empty, nonconsenting request returned
ADMISSION_DENIED with zero PNG bytes. MCP discovery in this chat now includes
capture_plugin_page.

The actual installed Capture/Browser modules also loaded in one corrected local
off-record fixture, and its480x320 PNG was inspected. The first fixture failed
its absolute import URL before consumer execution; corrected file URL succeeded.
Offscreen Vulkan/GPU warnings remain explicit. This is module/import evidence,
not production account image evidence.

Post-restart shell ping and original27x26 bar trigger passed. Browser is STOPPED
with zero views, popup hidden; the restart discarded warm in-memory page state
under the user's waiver. Persistent login/profile storage was never read, copied
or deleted; login recovery has not been observed. The bridge is installed and
loaded, not merely prepared. No authenticated image, hidden popup open, page
action, external image transmission, commit or push occurred. Evidence/backup:
`/home/slovn/.local/share/qml-preview-capture/activation-ty6zmrut/activation.json`.

The earlier broad blocked status is superseded: deployment is complete; only
authenticated pixel/interaction coverage remains unperformed. The earlier claim
that a restart was necessarily required before investigating an already present
Loader was too strong. Warm activation was tried and failed on actual host cache
behavior, rather than being declared impossible from assumption.

A concurrent external restart then changed the host PID and left an inert socket
(connection refused). The bridge failed closed on that pre-existing endpoint.
Recovery exposed two coordinator defects: a failed precheck did not stop a chained
shell restart, and an immediate startup probe used too short a deadline. The
corrected guarded Python sequence removed only the exact owned refused socket;
the final ready-host probe passed with PID485965, matching SO_PEERCRED, and
ADMISSION_DENIED with no PNG. Three task-issued restarts total were used, plus
one observed external restart; the original one-restart budget was exceeded.
Do not call that a clean lifecycle/budget PASS. Final trigger is visible27x26,
browser STOPPED, bridge loaded. No authenticated image was produced.
The native stale-endpoint-on-abrupt-restart limitation remains documented; this
activation did not broaden automatic socket takeover permissions.
