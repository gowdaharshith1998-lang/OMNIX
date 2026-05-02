/**
 * Galaxy-level graph model + force layout — mirrors viewerEngine.ts (canvas2d).
 * # NOTE: Keep aligned with buildGraphModel / startSimulation galaxy branch when touching viewerEngine.
 */
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";

export const OMNIX_GALAXY_COLORS = {
  directory: 0x6366f1,
  filePython: 0x3b82f6,
  fileTS: 0x06b6d4,
  fileMixed: 0x8b5cf6,
  edgeCalls: 0x4ade80,
  edgeImports: 0xf97316,
  edgeDefines: 0x3b82f6,
  edgeInherits: 0xa855f7,
  edgeDecorates: 0xf472b6,
  edgeDefault: 0x475569,
} as const;

export const OMNIX_LINK_HEX: Record<string, number> = {
  CALLS: OMNIX_GALAXY_COLORS.edgeCalls,
  IMPORTS: OMNIX_GALAXY_COLORS.edgeImports,
  DEFINES: OMNIX_GALAXY_COLORS.edgeDefines,
  INHERITS: OMNIX_GALAXY_COLORS.edgeInherits,
  DECORATES: OMNIX_GALAXY_COLORS.edgeDecorates,
};

const MAX_GALAXY_DIRS = 78;
export const GALAXY_ZOOM_MIN = 0.3;
export const GALAXY_ZOOM_MAX = 5.0;
const FIT_PAD = 0.85;

function dirname(path: string): string {
  if (!path) return "";
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 1) return "";
  parts.pop();
  return parts.join("/");
}

function basename(path: string): string {
  if (!path) return "";
  const parts = path.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function extLang(file: string): "py" | "ts" | "other" {
  const m = (file || "").match(/\.([a-z0-9]+)$/i);
  const e = m ? m[1].toLowerCase() : "";
  if (e === "py") return "py";
  if (
    e === "ts" ||
    e === "tsx" ||
    e === "js" ||
    e === "jsx" ||
    e === "mjs" ||
    e === "cjs"
  )
    return "ts";
  return "other";
}

function hexToRgb(hex: number) {
  return {
    r: (hex >> 16) & 255,
    g: (hex >> 8) & 255,
    b: hex & 255,
  };
}

function lerpColor(fromHex: number, toHex: number, t: number): number {
  const A = hexToRgb(fromHex);
  const B = hexToRgb(toHex);
  const r = Math.round(A.r + (B.r - A.r) * t);
  const g = Math.round(A.g + (B.g - A.g) * t);
  const b = Math.round(A.b + (B.b - A.b) * t);
  return (r << 16) | (g << 8) | b;
}

function directoryColor(types: { py: number; ts: number; other: number }): number {
  const py = types.py || 0;
  const ts = types.ts || 0;
  const tot = py + ts;
  if (tot === 0) return OMNIX_GALAXY_COLORS.directory;
  if (py > 0 && ts === 0) return OMNIX_GALAXY_COLORS.filePython;
  if (ts > 0 && py === 0) return OMNIX_GALAXY_COLORS.fileTS;
  const ratio = py / tot;
  return lerpColor(OMNIX_GALAXY_COLORS.fileTS, OMNIX_GALAXY_COLORS.filePython, ratio);
}

export type RawGraphNode = Record<string, unknown> & { id?: string; file?: string };
export type RawGraphLink = Record<string, unknown> & {
  source?: unknown;
  target?: unknown;
  type?: string;
};

export function sanitizeGraphPayload(data: {
  nodes?: unknown;
  links?: unknown;
  stats?: Record<string, unknown>;
}): {
  nodes: RawGraphNode[];
  links: RawGraphLink[];
  stats: Record<string, unknown>;
} {
  const nodes = Array.isArray(data.nodes) ? (data.nodes as RawGraphNode[]) : [];
  const links = Array.isArray(data.links) ? (data.links as RawGraphLink[]) : [];
  const ids = new Set(nodes.map((n) => n.id).filter(Boolean) as string[]);
  const cleanLinks = links.filter((l) => {
    const s =
      typeof l.source === "object" && l.source && "id" in (l.source as object)
        ? String((l.source as { id: string }).id)
        : String(l.source);
    const t =
      typeof l.target === "object" && l.target && "id" in (l.target as object)
        ? String((l.target as { id: string }).id)
        : String(l.target);
    return Boolean(s && t && ids.has(s) && ids.has(t));
  });
  return { nodes, links: cleanLinks, stats: data.stats || {} };
}

export type GalaxyGraphModel = ReturnType<typeof buildGalaxyGraphModel>;

export function buildGalaxyGraphModel(raw: {
  nodes: RawGraphNode[];
  links: RawGraphLink[];
}) {
  const nodeById = new Map<string, RawGraphNode>();
  raw.nodes.forEach((n) => {
    if (n.id) nodeById.set(String(n.id), n);
  });

  function nodeDir(n: RawGraphNode): string {
    const f = typeof n.file === "string" ? n.file : "";
    return dirname(f);
  }

  const dirMap = new Map<
    string,
    {
      id: string;
      name: string;
      childCount: number;
      types: Record<string, number>;
      lang: { py: number; ts: number; other: number };
    }
  >();

  function ensureDir(d: string | null) {
    if (!d && d !== "") return null;
    if (!dirMap.has(d!)) {
      dirMap.set(d!, {
        id: d!,
        name: basename(d!) || d! || "root",
        childCount: 0,
        types: { function: 0, class: 0, method: 0, import: 0, file: 0, other: 0 },
        lang: { py: 0, ts: 0, other: 0 },
      });
    }
    return dirMap.get(d!)!;
  }

  raw.nodes.forEach((n) => {
    const d = nodeDir(n);
    if (d === null || d === undefined) return;
    const rec = ensureDir(d);
    if (!rec) return;
    const t = typeof n.type === "string" ? n.type : "";
    if (
      t === "function" ||
      t === "class" ||
      t === "method" ||
      t === "import" ||
      t === "file"
    ) {
      rec.childCount += 1;
      if (rec.types[t] != null) rec.types[t] += 1;
      else rec.types.other = (rec.types.other || 0) + 1;
    }
    const f = typeof n.file === "string" ? n.file : "";
    if (f) {
      const L = extLang(f);
      if (L === "py") rec.lang.py += 1;
      else if (L === "ts") rec.lang.ts += 1;
      else rec.lang.other += 1;
    }
  });

  const dirEdges = new Map<
    string,
    {
      source: string;
      target: string;
      weight: number;
      types: Record<string, number>;
    }
  >();

  function edgeKey(a: string, b: string) {
    return a < b ? `${a}\t${b}` : `${b}\t${a}`;
  }

  raw.links.forEach((l) => {
    const sid =
      typeof l.source === "object" && l.source && "id" in (l.source as object)
        ? String((l.source as { id: string }).id)
        : String(l.source);
    const tid =
      typeof l.target === "object" && l.target && "id" in (l.target as object)
        ? String((l.target as { id: string }).id)
        : String(l.target);
    const sn = nodeById.get(sid);
    const tn = nodeById.get(tid);
    if (!sn || !tn) return;
    const da = nodeDir(sn);
    const db = nodeDir(tn);
    if (!da && !db) return;
    if (da === db) return;
    const k = edgeKey(da || "_", db || "_");
    if (!dirEdges.has(k)) {
      dirEdges.set(k, {
        source: da || "_",
        target: db || "_",
        weight: 0,
        types: {},
      });
    }
    const e = dirEdges.get(k)!;
    e.weight += 1;
    const lt = typeof l.type === "string" ? l.type : "CALLS";
    e.types[lt] = (e.types[lt] || 0) + 1;
  });

  const dirsSorted = [...dirMap.values()]
    .filter((d) => d.childCount > 0)
    .sort((a, b) => b.childCount - a.childCount);

  const topDirs = dirsSorted.slice(0, MAX_GALAXY_DIRS);
  const visibleDirSet = new Set(topDirs.map((d) => d.id));

  const galaxyNodes = topDirs.map((d) => ({
    id: "dir:" + d.id,
    kind: "directory" as const,
    dirId: d.id,
    name: d.name,
    label: d.name,
    childCount: d.childCount,
    types: { ...d.types },
    lang: { ...d.lang },
    color: directoryColor(d.lang),
    radius: 18 + Math.sqrt(d.childCount) * 1.2,
  }));

  const galaxyLinks: Array<{
    source: string;
    target: string;
    weight: number;
    type: string;
  }> = [];

  dirEdges.forEach((e) => {
    if (!visibleDirSet.has(e.source) || !visibleDirSet.has(e.target)) return;
    if (e.source === e.target) return;
    galaxyLinks.push({
      source: "dir:" + e.source,
      target: "dir:" + e.target,
      weight: e.weight,
      type:
        Object.keys(e.types).sort(
          (a, b) => (e.types[b] || 0) - (e.types[a] || 0)
        )[0] || "CALLS",
    });
  });

  const maxEdgeWeight = galaxyLinks.length
    ? Math.max(...galaxyLinks.map((e) => e.weight || 1))
    : 1;
  for (const node of galaxyNodes) {
    const nid = node.id;
    (node as { totalEdgeWeight?: number }).totalEdgeWeight = galaxyLinks
      .filter((e) => e.source === nid || e.target === nid)
      .reduce((sum, e) => sum + (e.weight || 1), 0);
  }
  const maxNodeWeight = galaxyNodes.length
    ? Math.max(
        ...galaxyNodes.map(
          (n) => (n as { totalEdgeWeight?: number }).totalEdgeWeight || 0
        ),
        1
      )
    : 1;

  return {
    galaxy: { nodes: galaxyNodes, links: galaxyLinks },
    maxEdgeWeight,
    maxNodeWeight,
  };
}

export type GalaxySimNode = {
  id: string;
  kind: string;
  x?: number;
  y?: number;
  radius?: number;
  color?: number;
  childCount?: number;
  vx?: number;
  vy?: number;
  index?: number;
  fx?: number | null;
  fy?: number | null;
};

/** Link datum for galaxy layout (extends d3-force link with edge metadata). */
export type GalaxySimLink = SimulationLinkDatum<GalaxySimNode> & {
  type?: string;
  weight?: number;
};

export function runGalaxyForceLayout(
  galaxyNodes: Array<Record<string, unknown>>,
  galaxyLinks: Array<{
    source: string;
    target: string;
    weight?: number;
    type?: string;
  }>
): {
  nodes: GalaxySimNode[];
  links: GalaxySimLink[];
} {
  const simNodes: GalaxySimNode[] = galaxyNodes.map((n) =>
    Object.assign({}, n)
  ) as GalaxySimNode[];
  const simLinks: GalaxySimLink[] = galaxyLinks.map((l) => ({
    source: l.source,
    target: l.target,
    type: l.type,
    weight: l.weight,
  }));

  if (!simNodes.length) {
    return { nodes: [], links: [] };
  }

  const simulation = forceSimulation(simNodes as SimulationNodeDatum[])
    .force("charge", forceManyBody().strength(-150))
    .force("center", forceCenter(0, 0))
    .force(
      "collide",
      forceCollide<GalaxySimNode>().radius((d: GalaxySimNode) => {
        const mass = d.childCount || 10;
        return 8 + Math.sqrt(mass) * 1.5;
      })
    )
    .alphaDecay(0.022)
    .velocityDecay(0.6);

  if (simLinks.length) {
    simulation.force(
      "link",
      forceLink<GalaxySimNode, GalaxySimLink>(simLinks)
        .id((d: GalaxySimNode) => d.id)
        .distance((l: GalaxySimLink) => {
          const w = l.weight || 1;
          return 40 + 120 / Math.sqrt(w + 1);
        })
        .strength(0.5)
    );
  }

  simulation.alpha(1);
  for (let i = 0; i < 120; i++) {
    simulation.tick();
  }
  simulation.stop();

  return {
    nodes: simNodes,
    links: simLinks,
  };
}

export function edgeColorForType(linkType: string): number {
  return OMNIX_LINK_HEX[linkType] ?? OMNIX_GALAXY_COLORS.edgeDefault;
}

/** Match viewerEngine fitWorldToNodes scale + center (galaxy, y-down coords). */
export function computeGalaxyCanvasFit(
  nodes: Array<{ x: number; y: number; radius?: number }>,
  viewportWidth: number,
  viewportHeight: number
): { cx: number; cy: number; scale: number } {
  if (!nodes.length) {
    return { cx: 0, cy: 0, scale: 1 };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    const r = n.radius ?? 12;
    minX = Math.min(minX, n.x - r);
    maxX = Math.max(maxX, n.x + r);
    minY = Math.min(minY, n.y - r);
    maxY = Math.max(maxY, n.y + r);
  }
  const bw = maxX - minX || 1;
  const bh = maxY - minY || 1;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const sx = (viewportWidth * FIT_PAD) / bw;
  const sy = (viewportHeight * FIT_PAD) / bh;
  let s = Math.min(sx, sy);
  s = Math.max(GALAXY_ZOOM_MIN, Math.min(GALAXY_ZOOM_MAX, s));
  return { cx, cy, scale: s };
}
