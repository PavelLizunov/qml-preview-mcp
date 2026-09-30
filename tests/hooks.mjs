import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import plugin from "../integrations/opencode-visual-cycle.mjs";

const root = await mkdtemp(path.join(os.tmpdir(), "qml-preview-hooks-"));
try {
  const hooks = await plugin({ directory: root });
  let system = { system: [] };
  await hooks["experimental.chat.system.transform"]({ sessionID: "ordinary" }, system);
  assert.equal(system.system.length, 0, "Ordinary project must not get plugin instructions");
  await writeFile(path.join(root, "manifest.json"), JSON.stringify({ kinds: ["bar-widget"], entryPoints: { "bar-widget": "Widget.qml" } }));
  system = { system: [] };
  await hooks["experimental.chat.system.transform"]({ sessionID: "plugin" }, system);
  assert.match(system.system[0], /healthcheck\/render_qml/);
  assert.match(system.system[0], /anti-slop/);
  const edit = { output: "Edited", metadata: {} };
  await hooks["tool.execute.after"]({ sessionID: "plugin", tool: "apply_patch", args: { patchText: "*** Update File: Widget.qml" } }, edit);
  assert.match(edit.output, /Plugin visual checkpoint/);
  const backend = { output: "Edited", metadata: {} };
  await hooks["tool.execute.after"]({ sessionID: "plugin", tool: "edit", args: { filePath: "helper.py" } }, backend);
  assert.equal(backend.output, "Edited");
  const compact = { context: [] };
  await hooks["experimental.session.compacting"]({ sessionID: "plugin" }, compact);
  assert.match(compact.context[0], /UI changes occurred/);
  assert.match(compact.context[0], /blockers, never a visual PASS/);
  assert.match(compact.context[0], /unchanged dependencies/);
  const other = path.join(root, "other");
  await mkdir(other);
  const explicit = await plugin({ directory: other });
  await explicit["tool.execute.after"]({ sessionID: "loaded", tool: "skill", args: { name: "omarchy-plugin-patterns" } }, { output: "Loaded", metadata: {} });
  system = { system: [] };
  await explicit["experimental.chat.system.transform"]({ sessionID: "loaded" }, system);
  assert.equal(system.system.length, 1, "Loading an owning skill activates reminders outside a manifest root");
  console.log("PASS: hooks scope, UI edit reminders, backend-only exclusion, missing/stale evidence rules, compaction and skill activation");
} finally {
  await rm(root, { recursive: true, force: true });
}
