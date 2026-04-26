import type { editor } from "monaco-editor";

/** Dark editor chrome aligned to analyze viewer / --omnix-bg-primary */
const BG = "#020615";
const FG = "#e2e8f0";
const MUTED = "#64748b";
const CYAN = "#22d3ee";
const INDIGO = "#6366f1";
const AMBER = "#f59e0b";
const RUBY = "#f87171";

const rules: editor.ITokenThemeRule[] = [
  { token: "", foreground: "e2e8f0" },
  { token: "comment", foreground: "64748b" },
  { token: "keyword", foreground: "a78bfa" },
  { token: "string", foreground: "4ade80" },
  { token: "number", foreground: "f59e0b" },
  { token: "regexp", foreground: "f472b6" },
  { token: "type", foreground: "22d3ee" },
  { token: "class", foreground: "a855f7" },
  { token: "function", foreground: "4ade80" },
  { token: "namespace", foreground: "6366f1" },
  { token: "variable", foreground: "e2e8f0" },
  { token: "type.identifier", foreground: "22d3ee" },
  { token: "variable.predefined", foreground: "f97316" },
  { token: "delimiter", foreground: "94a3b8" },
  { token: "invalid", foreground: "f87171" },
];

const colors: Record<string, string> = {
  "editor.background": BG,
  "editor.foreground": FG,
  "editorLineNumber.foreground": MUTED,
  "editorLineNumber.activeForeground": "94a3b8",
  "editorCursor.foreground": CYAN,
  "editor.selectionBackground": `${INDIGO}33`,
  "editor.inactiveSelectionBackground": `${INDIGO}22`,
  "editor.lineHighlightBackground": `${INDIGO}12`,
  "editorWhitespace.foreground": `${MUTED}55`,
  "editorWidget.background": "#0a0f1a",
  "editorWidget.border": `${INDIGO}44`,
  "editorError.foreground": RUBY,
  "editorWarning.foreground": AMBER,
  "minimap.background": "#020615",
};

/**
 * Call once per Monaco runtime before mounting editors.
 */
export function registerOmnixMonacoTheme(monaco: typeof import("monaco-editor")) {
  monaco.editor.defineTheme("omnix-dark", {
    base: "vs-dark",
    inherit: true,
    rules,
    colors,
  });
}
