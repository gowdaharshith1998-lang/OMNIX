import type { GraphNode } from "@/types/drilldown";
import type { XRayIssue } from "@/lib/xray_diagnostics";
import type { XRayInnerTab } from "./XRayItabs";
import { AgentTab } from "./inspector/AgentTab";
import { BrainTabContent } from "./inspector/BrainTabContent";
import { EntityHistoryTab } from "./inspector/EntityHistoryTab";
import { ReceiptsTab } from "./inspector/ReceiptsTab";

type Conn = {
  direction: "out" | "in";
  name: string;
  path: string;
  type: string;
};

type ScopeModel = {
  connections: Conn[];
  incoming: number;
  outgoing: number;
  dark: number;
};

type Props = {
  active: XRayInnerTab;
  workspaceId: string;
  scopeAtomId: string;
  selectedNode: GraphNode | null;
  scopeModel: ScopeModel;
  issues: XRayIssue[];
  filesystemHygieneCleanLine: string | null;
  onSuggestedAction: () => void;
};

export function XRayContent({
  active,
  workspaceId,
  scopeAtomId,
  selectedNode,
  scopeModel,
  issues,
  filesystemHygieneCleanLine,
  onSuggestedAction,
}: Props) {
  if (active === "agent") {
    return <AgentTab />;
  }

  if (active === "receipts") {
    return <ReceiptsTab />;
  }

  if (active === "history") {
    return <EntityHistoryTab />;
  }

  void scopeAtomId;
  void issues;
  void filesystemHygieneCleanLine;
  void onSuggestedAction;

  return (
    <BrainTabContent
      workspaceId={workspaceId}
      selectedNode={selectedNode}
      scopeModel={scopeModel}
    />
  );
}
