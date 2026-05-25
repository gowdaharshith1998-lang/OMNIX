/**
 * Cutover-eligibility selector — a graph node can be shifted only when:
 *   - replication_status === "verified"
 *   - a candidate Service is deployed for it (presence flag from the graph store)
 *
 * The selector is exported standalone so the CutoverModal trigger logic
 * and the LeftRail's "eligible units" picker share the same predicate.
 */

export interface CutoverEligibleNode {
  id: string;
  unit: string;
  replication_status: "in_progress" | "verified" | "rejected" | "unknown";
  candidate_service: boolean;
}

export function isCutoverEligible(node: Pick<CutoverEligibleNode, "replication_status" | "candidate_service">): boolean {
  return node.replication_status === "verified" && node.candidate_service === true;
}

export function selectEligibleUnits(nodes: CutoverEligibleNode[]): CutoverEligibleNode[] {
  return nodes.filter((n) => isCutoverEligible(n));
}
