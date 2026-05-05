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
): { cl: Cluster; d: number } | null {
  let best: { cl: Cluster; d: number } | null = null;
  for (const cl of clusters) {
    const d = Math.sqrt(dist2(cx, cy, cl.cx, cl.cy));
    if (d <= cl.radius && (!best || d < best.d)) {
      best = { cl, d };
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

  type Cell = { col: number; row: number; cx: number; cy: number; key: string };
  const inside: Cell[] = [];
  const colMin = -2;
  const colMax = approxCols + 2;
  const rowMin = -2;
  const rowMax = approxRows + 2;

  for (let row = rowMin; row <= rowMax; row++) {
    for (let col = colMin; col <= colMax; col++) {
      const { cx, cy } = hexCenter(col, row, size, originX, originY);
      if (!insideEllipse(cx, cy, spec.envelopeCx, spec.envelopeCy, spec.envelopeRx, spec.envelopeRy)) continue;
      inside.push({ col, row, cx, cy, key: hexKey(col, row) });
    }
  }

  const isData = new Map<string, boolean>();
  const clusterOf = new Map<string, string | undefined>();

  for (const c of inside) {
    const own = owningCluster(c.cx, c.cy, spec.clusters);
    clusterOf.set(c.key, own?.cl.id);
    if (own) {
      isData.set(c.key, rng() < own.cl.density);
    } else {
      isData.set(c.key, false);
    }
  }

  const countDF = () => {
    let d = 0;
    let f = 0;
    for (const c of inside) {
      if (isData.get(c.key)) d++;
      else f++;
    }
    return { d, f };
  };

  let { d: dataCount, f: fillerCount } = countDF();
  let ratio = dataCount === 0 ? ratioMax : fillerCount / Math.max(1, dataCount);

  const farFromCluster = (c: Cell) => {
    const clId = clusterOf.get(c.key);
    const cl = spec.clusters.find((k) => k.id === clId);
    const cx = cl ? cl.cx : spec.envelopeCx;
    const cy = cl ? cl.cy : spec.envelopeCy;
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
        .filter((c) => isData.get(c.key))
        .sort((a, b) => farFromCluster(b) - farFromCluster(a));
      const need = Math.min(dataSorted.length, Math.ceil(D * ratioMin - F));
      for (let i = 0; i < need; i++) isData.set(dataSorted[i].key, false);
    } else if (r > ratioMax) {
      const fillerNear = inside
        .filter((c) => !isData.get(c.key) && clusterOf.get(c.key))
        .map((c) => {
          const cl = spec.clusters.find((k) => k.id === clusterOf.get(c.key))!;
          return { c, near: dist2(c.cx, c.cy, cl.cx, cl.cy) };
        })
        .sort((a, b) => a.near - b.near);
      const need = Math.min(fillerNear.length, Math.floor(F - D * ratioMax));
      for (let i = 0; i < need; i++) isData.set(fillerNear[i].c.key, true);
    }
  };

  rebalanceRatio();

  const hexes: Hex[] = inside.map((c) => ({
    id: c.key,
    cx: c.cx,
    cy: c.cy,
    isData: !!isData.get(c.key),
    clusterId: clusterOf.get(c.key),
    neighbors: [],
  }));

  const hexMap = new Map(hexes.map((h) => [h.id, h]));
  for (const h of hexes) {
    const [col, row] = h.id.split('_').map(Number);
    const nbrs: string[] = [];
    for (const [dc, dr] of neighborOffsets(col, row)) {
      const nk = hexKey(dc, dr);
      if (hexMap.has(nk)) nbrs.push(nk);
    }
    h.neighbors = nbrs;
  }

  return hexes;
}
