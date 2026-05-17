import type {
  ActionContext,
  ActionDescriptor,
  ActionRegistry,
  ToolName,
} from "./types";

const impactTools: ToolName[] = [
  "get_node_context",
  "find_callers",
  "find_callees",
  "find_related_files",
];
const codeTools: ToolName[] = ["get_node_context", "read_code_region"];
const allTools: ToolName[] = [
  "get_node_context",
  "find_callers",
  "find_callees",
  "find_related_files",
  "read_code_region",
];

function selectedArgs(ctx: ActionContext): Record<string, unknown> {
  return {
    node_id: ctx.selectedNode?.id,
    file_path: ctx.selectedNode?.file_path,
    line_start: ctx.selectedNode?.line_start,
    line_end: ctx.selectedNode?.line_end,
  };
}

function sourceSummary(ctx: ActionContext) {
  const node = ctx.selectedNode;
  const issue = ctx.issue;
  return [
    `Workspace: ${ctx.workspaceId}`,
    node ? `Selected: ${node.type} ${node.name} at ${node.file_path}:${node.line_start}` : "",
    issue ? `Diagnostic: ${issue.title}\nDetail: ${issue.detail}\nSuggested action: ${issue.action}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function base(ctx: ActionContext, id: string, title: string, tools: ToolName[]) {
  return {
    id,
    title,
    workspaceId: ctx.workspaceId,
    projectId: ctx.projectId,
    source: { kind: "card" as const, cardId: "xray" },
    tools,
    toolArgs: selectedArgs(ctx),
  };
}

function capturedApply() {
  window.dispatchEvent(
    new CustomEvent("omnix:action-toast", {
      detail: "proposal captured — diff application lands in 15.4",
    })
  );
}

export const ACTION_REGISTRY: ActionRegistry = {
  "xray.diagnostics.god_file.split": (ctx) => ({
    ...base(ctx, "xray.diagnostics.god_file.split", "Split God File", codeTools),
    kind: "decision",
    prompt:
      `${sourceSummary(ctx)}\n\nPropose a split into 3-5 focused modules. ` +
      "Include module names, moved responsibilities, migration order, and risks.",
    applyLabel: "Apply split",
    cancelLabel: "Cancel",
    onApply: capturedApply,
  }),

  "xray.diagnostics.high_complexity.extract": (ctx) => ({
    ...base(
      ctx,
      "xray.diagnostics.high_complexity.extract",
      "Extract Sub-Modules",
      codeTools
    ),
    kind: "agent",
    prompt:
      `${sourceSummary(ctx)}\n\nSuggest sub-module extractions that reduce complexity. ` +
      "Prioritize low-risk seams and explain the first safe step.",
  }),

  "xray.diagnostics.high_fan_in.versioned_interfaces": (ctx) => ({
    ...base(
      ctx,
      "xray.diagnostics.high_fan_in.versioned_interfaces",
      "Version Interfaces",
      impactTools
    ),
    kind: "decision",
    prompt:
      `${sourceSummary(ctx)}\n\nPropose versioned interfaces for this high fan-in scope. ` +
      "Include compatibility plan, caller migration order, and breakage risks.",
    applyLabel: "Capture proposal",
    cancelLabel: "Cancel",
    onApply: capturedApply,
  }),

  "xray.diagnostics.entanglement.explain": (ctx) => ({
    ...base(ctx, "xray.diagnostics.entanglement.explain", "Explain Entanglement", impactTools),
    kind: "agent",
    prompt:
      `${sourceSummary(ctx)}\n\nExplain why this code is coupled in 3-5 sentences. ` +
      "Use graph relationships when available and name the most important files.",
  }),

  "xray.diagnostics.dark_matter.investigate": (ctx) => ({
    ...base(ctx, "xray.diagnostics.dark_matter.investigate", "Investigate Dark Matter", impactTools),
    kind: "agent",
    prompt:
      `${sourceSummary(ctx)}\n\nInvestigate why this code has hidden runtime/config dependencies. ` +
      "Call out likely env/config/middleware sources and validation steps.",
  }),

  "xray.diagnostics.high_fan_out.facade": (ctx) => ({
    ...base(ctx, "xray.diagnostics.high_fan_out.facade", "Facade Proposal", impactTools),
    kind: "agent",
    prompt:
      `${sourceSummary(ctx)}\n\nSuggest a facade or mediator plan for this high fan-out scope. ` +
      "Rank dependencies to hide first and explain tradeoffs.",
  }),

  "xray.diagnostics.orphan_module.investigate": (ctx) => ({
    ...base(ctx, "xray.diagnostics.orphan_module.investigate", "Investigate Orphan", impactTools),
    kind: "agent",
    prompt:
      `${sourceSummary(ctx)}\n\nInvestigate whether this isolated module is dead code, generated code, ` +
      "or missing graph links. Provide concrete verification steps.",
  }),

  "xray.agent.explain_selection": (ctx) => ({
    ...base(ctx, "xray.agent.explain_selection", "Explain Selection", allTools),
    kind: "agent",
    prompt:
      `${sourceSummary(ctx)}\n\nExplain the selected code in plain English. ` +
      "Use caller/callee and related-file tools when relevant.",
  }),

  "bugs.explain_finding": (ctx) => ({
    id: "bugs.explain_finding",
    title: "Explain Finding",
    workspaceId: ctx.workspaceId,
    projectId: ctx.projectId,
    source: { kind: "drawer", drawerId: "bugs" },
    tools: ["read_code_region"],
    toolArgs: {
      file_path: ctx.finding?.file,
      line_start: ctx.finding?.lineno,
      line_end: ctx.finding?.lineno ? ctx.finding.lineno + 80 : undefined,
    },
    kind: "agent",
    prompt:
      `Bug finding: ${JSON.stringify(ctx.finding ?? {}, null, 2)}\n\n` +
      "Explain why this finding was flagged and suggest the safest next debugging step.",
  }),

  "rightrail.new_agent": (ctx) => ({
    id: "rightrail.new_agent",
    title: "New Agent",
    workspaceId: ctx.workspaceId,
    projectId: ctx.projectId,
    source: { kind: "rail", railId: "right" },
    tools: allTools,
    toolArgs: selectedArgs(ctx),
    kind: "agent",
    prompt:
      (ctx.userPrompt || "Summarize this workspace.") +
      "\n\nUse code and graph tools when they improve the answer.",
  }),
};

export function actionIdForXRayIssue(title: string): string {
  const t = title.toLowerCase();
  if (t.includes("god file")) return "xray.diagnostics.god_file.split";
  if (t.includes("complexity")) return "xray.diagnostics.high_complexity.extract";
  if (t.includes("fan-in")) return "xray.diagnostics.high_fan_in.versioned_interfaces";
  if (t.includes("entangled")) return "xray.diagnostics.entanglement.explain";
  if (t.includes("dark matter")) return "xray.diagnostics.dark_matter.investigate";
  if (t.includes("fan-out")) return "xray.diagnostics.high_fan_out.facade";
  if (t.includes("orphan")) return "xray.diagnostics.orphan_module.investigate";
  return "xray.agent.explain_selection";
}

export function createActionDescriptor(
  actionId: string,
  context: ActionContext
): ActionDescriptor | null {
  const factory = ACTION_REGISTRY[actionId];
  if (!factory) return null;
  return factory(context);
}
