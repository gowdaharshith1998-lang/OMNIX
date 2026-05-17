import type { ReactNode } from "react";
import type { BugFinding } from "@/lib/api";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import type { XRayIssue } from "@/lib/xray_diagnostics";

export type ActionKind = "agent" | "decision";

export type ToolName =
  | "get_node_context"
  | "find_callers"
  | "find_callees"
  | "find_related_files"
  | "read_code_region";

export type ActionSource =
  | { kind: "card"; cardId: string }
  | { kind: "drawer"; drawerId: string }
  | { kind: "rail"; railId: string };

export type ActionContext = {
  workspaceId: string;
  projectId?: string;
  projectPath?: string;
  selectedNode?: GraphNode | null;
  scopedNodes?: GraphNode[];
  scopedEdges?: GraphEdge[];
  issue?: XRayIssue;
  finding?: BugFinding;
  userPrompt?: string;
};

export interface BaseActionDescriptor {
  id: string;
  title: string;
  prompt: string;
  workspaceId: string;
  projectId?: string;
  provider?: string;
  model?: string;
  systemPrompt?: string;
  source: ActionSource;
  tools?: ToolName[];
  toolArgs?: Record<string, unknown>;
}

export interface AgentActionDescriptor extends BaseActionDescriptor {
  kind: "agent";
}

export interface DecisionActionDescriptor extends BaseActionDescriptor {
  kind: "decision";
  applyLabel: string;
  cancelLabel: string;
  onApply: (result: ActionResult) => void | Promise<void>;
}

export type ActionDescriptor = AgentActionDescriptor | DecisionActionDescriptor;

export type ToolStep = {
  tool: ToolName | string;
  status: "ok" | "error" | "degraded" | string;
  result?: unknown;
  truncated?: boolean;
  error?: string | null;
  /** LLM round (0 = seed prefetch) */
  turn_number?: number;
  args_summary?: string;
  phase?: string;
  tool_call_id?: string | null;
};

export interface ActionResult {
  ok: boolean;
  text: string;
  provider: string;
  model: string;
  tokensIn: number;
  tokensOut: number;
  latencyMs: number;
  receiptId?: string;
  error?: string;
  errorClass?: string;
  errorMessage?: string;
  httpStatus?: number | null;
  retryable?: boolean;
  toolSteps: ToolStep[];
  costCapTriggered?: boolean;
  iterations?: number;
  capped?: boolean;
  capReason?: string | null;
}

export type ActionRegistry = Record<
  string,
  (context: ActionContext) => ActionDescriptor
>;

export type ActionButtonRender = ReactNode;

export function isAgentAction(d: ActionDescriptor): d is AgentActionDescriptor {
  return d.kind === "agent";
}

export function isDecisionAction(d: ActionDescriptor): d is DecisionActionDescriptor {
  return d.kind === "decision";
}
