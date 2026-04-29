export type DrillDownTarget =
  | { mode: "file"; path: string }
  | {
      mode: "node";
      nodeId: string;
      filePath: string;
      lineStart: number;
      lineEnd: number;
      name: string;
    };

export type GraphNode = {
  id: string;
  name: string;
  type: string;
  file_path: string | null;
  line_start: number;
  line_end: number;
};

export type GraphEdge = {
  id: string | number;
  source_id: string;
  target_id: string;
  relationship: string;
};
