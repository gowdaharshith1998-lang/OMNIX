/**
 * Pure brain-shaped hex envelope (slice-20). No Pixi / DOM.
 * Pointy-top hex grid, elliptical envelope, cluster bands, seeded RNG.
 */

export type Hex = {
  id: string;
  cx: number;
  cy: number;
  isData: boolean;
  clusterId?: string;
  neighbors: string[];
};

export type Cluster = {
  id: string;
  cx: number;
  cy: number;
  radius: number;
  density: number;
};

export type EnvelopeSpec = {
  canvasW: number;
  canvasH: number;
  hexRadius: number;
  envelopeRx: number;
  envelopeRy: number;
  envelopeCx: number;
  envelopeCy: number;
  clusters: Cluster[];
  fillerToDataRatio: [number, number];
  seed: number;
};

/** Mulberry32 — deterministic for tests */
export function mulberry32(a: number) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function insideEllipse(
  x: number,
  y: number,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
): boolean {
  const dx = (x - cx) / rx;
  const dy = (y - cy) / ry;
  return dx * dx + dy * dy <= 1;
}

/** 6 axial neighbors in offset coordinates */
export function neighborOffsets(col: number, row: number): Array<[number, number]> {
  const odd = row % 2 === 1;
  return odd
    ? [
        [col + 1, row],
        [col - 1, row],
        [col, row + 1],
        [col + 1, row + 1],
        [col, row - 1],
        [col + 1, row - 1],
      ]
    : [
        [col + 1, row],
        [col - 1, row],
        [col, row + 1],
        [col - 1, row + 1],
        [col, row - 1],
        [col - 1, row - 1],
      ];
}

function hexKey(col: number, row: number): string {
  return `${col}_${row}`;
}

/** Pointy-top hex center; `size` = circumradius */
export function hexCenter(col: number, row: number, size: number, ox: number, oy: number) {
  const w = Math.sqrt(3) * size;
  const cx = ox + w * (col + 0.5 * (row & 1));
  const cy = oy + 1.5 * size * row;
  return { cx, cy };
}

function dist2(ax: number, ay: number, bx: number, by: number) {
  const dx = ax - bx;
  const dy = ay - by;
  return dx * dx + dy * dy;
}

/** Nearest cluster whose circle contains the point, else null */
function owningCluster(
  cx: number,
  cy: number,
  clusters: Cluster[],
): { cl: Cluster; d2: number } | null {
  let best: { cl: Cluster; d2: number } | null = null;
  for (const cl of clusters) {
    const d2 = dist2(cx, cy, cl.cx, cl.cy);
    if (d2 <= cl.radius * cl.radius && (!best || d2 < best.d2)) {
      best = { cl, d2 };
    }
  }
  return best;
}

export function generateBrainEnvelope(spec: EnvelopeSpec): Hex[] {
  const rng = mulberry32(spec.seed);
  const size = spec.hexRadius;
  const [ratioMin, ratioMax] = spec.fillerToDataRatio;

  const gridW = spec.canvasW * 1.2;
  const gridH = spec.canvasH * 1.2;
  const approxCols = Math.ceil(gridW / (Math.sqrt(3) * size)) + 4;
  const approxRows = Math.ceil(gridH / (1.5 * size)) + 4;

  const originX = spec.envelopeCx - (approxCols * Math.sqrt(3) * size) / 2;
  const originY = spec.envelopeCy - (approxRows * 1.5 * size) / 2;

  type Cell = {
    col: number;
    row: number;
    cx: number;
    cy: number;
    key: string;
    cluster?: Cluster;
    clusterId?: string;
    isData: boolean;
  };
  const inside: Cell[] = [];
  const colMin = -2;
  const colMax = approxCols + 2;
  const rowMin = -2;
  const rowMax = approxRows + 2;

  for (let row = rowMin; row <= rowMax; row++) {
    for (let col = colMin; col <= colMax; col++) {
      const { cx, cy } = hexCenter(col, row, size, originX, originY);
      if (!insideEllipse(cx, cy, spec.envelopeCx, spec.envelopeCy, spec.envelopeRx, spec.envelopeRy)) continue;
      inside.push({ col, row, cx, cy, key: hexKey(col, row), isData: false });
    }
  }

  for (const c of inside) {
    const own = owningCluster(c.cx, c.cy, spec.clusters);
    if (own) {
      c.cluster = own.cl;
      c.clusterId = own.cl.id;
      c.isData = rng() < own.cl.density;
    }
  }

  const countDF = () => {
    let d = 0;
    let f = 0;
    for (const c of inside) {
      if (c.isData) d++;
      else f++;
    }
    return { d, f };
  };

  const farFromCluster = (c: Cell) => {
    const cx = c.cluster ? c.cluster.cx : spec.envelopeCx;
    const cy = c.cluster ? c.cluster.cy : spec.envelopeCy;
    return dist2(c.cx, c.cy, cx, cy);
  };

  /** Single-pass ratio trim — avoids O(n²) iterative demote (slice-20 perf budget). */
  const rebalanceRatio = () => {
    let { d: D, f: F } = countDF();
    if (D === 0) return;
    let r = F / D;
    if (r >= ratioMin && r <= ratioMax) return;
    if (r < ratioMin) {
      const dataSorted = inside
        .filter((c) => c.isData)
        .sort((a, b) => farFromCluster(b) - farFromCluster(a));
      const need = Math.min(dataSorted.length, Math.ceil(D * ratioMin - F));
      for (let i = 0; i < need; i++) dataSorted[i].isData = false;
    } else if (r > ratioMax) {
      const fillerNear = inside
        .filter((c) => !c.isData && c.cluster)
        .map((c) => ({ c, near: dist2(c.cx, c.cy, c.cluster!.cx, c.cluster!.cy) }))
        .sort((a, b) => a.near - b.near);
      const need = Math.min(fillerNear.length, Math.floor(F - D * ratioMax));
      for (let i = 0; i < need; i++) fillerNear[i].c.isData = true;
    }
  };

  rebalanceRatio();

  const hexes: Hex[] = inside.map((c) => ({
    id: c.key,
    cx: c.cx,
    cy: c.cy,
    isData: c.isData,
    clusterId: c.clusterId,
    neighbors: [],
  }));

  const hexMap = new Map<string, Hex>();
  for (const h of hexes) hexMap.set(h.id, h);
  for (let i = 0; i < hexes.length; i++) {
    const h = hexes[i];
    const c = inside[i];
    const nbrs: string[] = [];
    for (const [dc, dr] of neighborOffsets(c.col, c.row)) {
      const nk = hexKey(dc, dr);
      if (hexMap.has(nk)) nbrs.push(nk);
    }
    h.neighbors = nbrs;
  }

  return hexes;
}
