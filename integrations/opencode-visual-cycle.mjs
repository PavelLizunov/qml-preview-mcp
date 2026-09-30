// Scoped reminders only. Never executes QML, dispatches agents, or changes permissions.
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const directive = `Plugin visual acceptance: load omarchy-plugin-patterns and its native design/visual references. Discover qml-preview healthcheck/render_qml. Inspect reviewed actual-consumer fixtures with inert models. Render after each coherent UI/text/state change and before delivery; inspect the PNG attachment or read the returned path, review native design and anti-slop, fix authorized defects, then rerender. Track dependency hashes, states, locale, logical/pixel geometry and DPR. No desktop capture, production panels, shell/theme changes or external image viewers for development previews. Missing tools/imports/safe fixtures are concrete blockers, never a visual PASS. Backend-only or read-only work does not authorize runtime checks. Current evidence can be reused only for unchanged dependencies. A tool call or image read does not prove design quality.`;

export default async ({ directory, worktree } = {}) => {
  const root = path.resolve(directory || worktree || ".");
  const states = new Map();

  async function pluginProject() {
    try {
      const file = path.join(root, "manifest.json");
      if ((await stat(file)).size > 65536) return false;
      const manifest = JSON.parse(await readFile(file, "utf8"));
      return Array.isArray(manifest.kinds) && manifest.entryPoints && typeof manifest.entryPoints === "object";
    } catch {
      return false;
    }
  }

  function state(id) {
    if (!states.has(id)) {
      // ponytail: bounded reminder state, oldest session evicted after 128 sessions.
      if (states.size >= 128) states.delete(states.keys().next().value);
      states.set(id, { active: false, dirty: false });
    }
    return states.get(id);
  }

  function uiChange(tool, args, output) {
    if (output.metadata?.error || output.metadata?.exit && output.metadata.exit !== 0) return false;
    if (tool === "apply_patch") {
      return /(?:Add|Update|Delete) File: [^\n]+\.(?:qml|js|ts|svg|json|po|tsv)\b/i.test(args.patchText || args.patch || "");
    }
    if (tool === "edit" || tool === "write") {
      return /\.(?:qml|js|ts|svg|json|po|tsv)$/i.test(args.filePath || "");
    }
    return false;
  }

  return {
    "tool.execute.after": async (input, output) => {
      const current = state(input.sessionID);
      if (input.tool === "skill" && ["omarchy-plugin", "omarchy-plugin-patterns"].includes(input.args?.name)) {
        current.active = true;
      }
      if (!current.active && await pluginProject()) current.active = true;
      if (!current.active || !uiChange(input.tool, input.args || {}, output)) return;
      current.dirty = true;
      output.output += "\n\n[Plugin visual checkpoint] UI-related source changed. After this coherent edit, call qml-preview on the reviewed actual consumer, inspect its image, and complete native design/anti-slop review. Rerender after corrections. Do not claim visual acceptance from file creation alone.";
    },
    "experimental.chat.system.transform": async (input, output) => {
      const current = state(input.sessionID || "project");
      if (!current.active && await pluginProject()) current.active = true;
      if (current.active) output.system.push(directive);
    },
    "experimental.session.compacting": async (input, output) => {
      const current = state(input.sessionID);
      if (!current.active && await pluginProject()) current.active = true;
      if (current.active) output.context.push(directive + (current.dirty ? " UI changes occurred: retain pending/reused evidence and review status explicitly." : ""));
    },
    event: async ({ event }) => {
      if (event.type === "session.deleted") states.delete(event.properties?.info?.id);
    },
  };
};
