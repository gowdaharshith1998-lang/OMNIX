import type { GraphNode } from "@/types/drilldown";
import type { XRayIssue } from "@/lib/xray_diagnostics";
import type { XRayInnerTab } from "./XRayItabs";
import { AgentTab } from "./inspector/AgentTab";
import { BrainTabContent } from "./inspector/BrainTabContent";
import { EntityHistoryTab } from "./inspector/EntityHistoryTab";
import { ReceiptsTab } from "./inspector/ReceiptsTab";
import { useWireEvents } from "@/lib/wireEventBuffer";

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
  const wireEvents = useWireEvents(workspaceId);

  if (active === "agent") {
    return <AgentTab events={wireEvents} />;
  }

  if (active === "receipts") {
    return <ReceiptsTab workspaceId={workspaceId} />;
  }

  if (active === "history") {
    // Phase 5 will replace stub body; for now still stubbed.
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
