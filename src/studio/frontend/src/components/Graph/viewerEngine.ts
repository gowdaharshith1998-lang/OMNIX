// @ts-nocheck
// Legacy graph engine transplanted into React Studio; hand-maintained until debt-16 cleanup.
import * as PIXI from "pixi.js";
import * as d3 from "d3";
import { gsap } from "gsap";
import {
  activateGalaxyStressTier,
  detectGalaxyStressTier,
  getActiveGalaxyStressTier,
} from "./galaxyStressHarness";
import { generateStressGraph } from "./syntheticStressGraph";
import { setOmnixFpsSample } from "./omnixViewerMetrics";

export function installOmnixViewerEngine(studio) {
  'use strict';

  const COLORS = {
    bg: 0x020615,
    bgGradientEnd: 0x0a0f1a,
    directory: 0x6366f1,
    filePython: 0x3b82f6,
    fileTS: 0x06b6d4,
    fileMixed: 0x8b5cf6,
    function: 0x4ade80,
    class: 0xa855f7,
    method: 0x22d3ee,
    import: 0xf97316,
    edgeCalls: 0x4ade80,
    edgeImports: 0xf97316,
    edgeDefines: 0x3b82f6,
    edgeInherits: 0xa855f7,
    edgeDecorates: 0xf472b6,
    edgeDefault: 0x475569,
    text: 0xe2e8f0,
    textDim: 0x64748b,
  };

  const LINK_HEX = {
    CALLS: COLORS.edgeCalls,
    IMPORTS: COLORS.edgeImports,
    DEFINES: COLORS.edgeDefines,
    INHERITS: COLORS.edgeInherits,
    DECORATES: COLORS.edgeDecorates,
  };

  const STORAGE_VISITED = 'omnix_visited';
  const MAX_GALAXY_DIRS = 78;
  const MAX_STAR_FILES = 50;
  const MAX_PLANET_SYMBOLS = 30;
  const MAX_POOL_NODES = 200;
  const MAX_DARK_MATTER_DRAW = 50;
  const MAX_DARK_FORCE_DRAW = 120;
  const MAX_ENTANGLED_DRAW = 100;
  const GALAXY_LABEL_POOL_SIZE = 30;
  const ZOOM_MIN = 0.3;
  const ZOOM_MAX = 5.0;
  /** Galaxy gravitational hover: min screen px radius from hex center; orbit area extends to orbit + pad */
  const GALAXY_WARP_RADIUS = 150;
  const GALAXY_ORBIT_HOVER_PAD_SCREEN = 30;
  const GALAXY_MAX_WARP_SCALE = 2.5;
  /** Baked galaxy directory hex texture radius; must match default `sn.radius || 20` scale divisor in syncPixiFromSim. */
  const HEX_BASE_RADIUS = 20;
  /** Baked radial glow: outer radius in local px; world radius is `(sn.radius || 12) * 2.5` via scale. */
  const GLOW_TEXTURE_BASE_RADIUS = 50;
  const GLOW_TEXTURE_RING_COUNT = 12;

  /** Screen-space pick radius: hex-center circle (150px) ∪ circle through full orbit (world orbit × scale + pad). */
  function galaxyDirectoryHoverScreenRadius(dirNode, worldScale) {
    if (!dirNode || dirNode.kind !== 'directory') return GALAXY_WARP_RADIUS;
    const wScale = dirNode._warpScale || 1;
    const baseR = dirNode.radius || 18;
    const orbitWorld = wScale * baseR * 3;
    const orbitScreen = orbitWorld * worldScale;
    return Math.max(GALAXY_WARP_RADIUS, orbitScreen + GALAXY_ORBIT_HOVER_PAD_SCREEN);
  }
  /** Keep directory file orbit visible briefly after pointer leaves hex + file hit zones */
  const STICKY_DELAY = 600;
  const SEARCH_DEBOUNCE_MS = 150;

  const GRAPH_API_URL = (function () {
    const proto = window.location.protocol;
    if (proto === 'file:' || !window.location.origin || window.location.origin === 'null') return null;
    return new URL('/api/graph', window.location.origin).href;
  })();

  const TIMELINE_API_URL = (function () {
    const proto = window.location.protocol;
    if (proto === 'file:' || !window.location.origin || window.location.origin === 'null') return null;
    return new URL('/api/timeline', window.location.origin).href;
  })();

  let aiAvailable = false;
  let aiProvider = '';
  let aiStatusPromise = null;

  function ensureAiStatus() {
    if (!aiStatusPromise) {
      const url = new URL('/api/ai/status', window.location.origin).href;
      aiStatusPromise = fetch(url, { cache: 'no-store' })
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
          if (data && data.available) {
            aiAvailable = true;
            aiProvider = data.provider || '';
          } else {
            aiAvailable = false;
            aiProvider = '';
          }
          return data;
        })
        .catch(() => ({}));
    }
    return aiStatusPromise;
  }

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function dirname(path) {
    if (!path) return '';
    const parts = path.split('/').filter(Boolean);
    if (parts.length <= 1) return '';
    parts.pop();
    return parts.join('/');
  }

  function basename(path) {
    if (!path) return '';
    const parts = path.split('/').filter(Boolean);
    return parts.length ? parts[parts.length - 1] : '';
  }

  function truncateGraphLabel(s, maxLen) {
    const t = s == null ? '' : String(s);
    if (t.length <= maxLen) return t;
    return t.slice(0, Math.max(0, maxLen - 1)) + '…';
  }

  function extLang(file) {
    const m = (file || '').match(/\.([a-z0-9]+)$/i);
    const e = m ? m[1].toLowerCase() : '';
    if (e === 'py') return 'py';
    if (e === 'ts' || e === 'tsx' || e === 'js' || e === 'jsx' || e === 'mjs' || e === 'cjs') return 'ts';
    return 'other';
  }

  function hexToRgb(hex) {
    return {
      r: (hex >> 16) & 255,
      g: (hex >> 8) & 255,
      b: hex & 255,
    };
  }

  function lerpColor(fromHex, toHex, t) {
    const A = hexToRgb(fromHex);
    const B = hexToRgb(toHex);
    const r = Math.round(A.r + (B.r - A.r) * t);
    const g = Math.round(A.g + (B.g - A.g) * t);
    const b = Math.round(A.b + (B.b - A.b) * t);
    return (r << 16) | (g << 8) | b;
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function directoryColor(types) {
    const py = types.py || 0;
    const ts = types.ts || 0;
    const tot = py + ts;
    if (tot === 0) return COLORS.directory;
    if (py > 0 && ts === 0) return COLORS.filePython;
    if (ts > 0 && py === 0) return COLORS.fileTS;
    const ratio = py / tot;
    return lerpColor(COLORS.fileTS, COLORS.filePython, ratio);
  }

  function sanitizePayload(data) {
    const nodes = Array.isArray(data.nodes) ? data.nodes : [];
    const links = Array.isArray(data.links) ? data.links : [];
    const ids = new Set(nodes.map(n => n.id).filter(Boolean));
    const cleanLinks = links.filter(l => {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      return s && t && ids.has(s) && ids.has(t);
    });
    return { nodes, links: cleanLinks, stats: data.stats || {} };
  }

  /** --- Build semantic levels from raw graph --- */
  function buildGraphModel(raw) {
    const nodeById = new Map();
    raw.nodes.forEach(n => nodeById.set(n.id, n));

    function nodeDir(n) {
      const f = n.file || '';
      return dirname(f);
    }

    const dirMap = new Map();
    function ensureDir(d) {
      if (!d && d !== '') return null;
      if (!dirMap.has(d)) {
        dirMap.set(d, {
          id: d,
          name: basename(d) || d || 'root',
          childCount: 0,
          types: { function: 0, class: 0, method: 0, import: 0, file: 0 },
          lang: { py: 0, ts: 0, other: 0 },
        });
      }
      return dirMap.get(d);
    }

    raw.nodes.forEach(n => {
      const d = nodeDir(n);
      if (d === null || d === undefined) return;
      const rec = ensureDir(d);
      if (!rec) return;
      const t = n.type || '';
      if (t === 'function' || t === 'class' || t === 'method' || t === 'import' || t === 'file') {
        rec.childCount += 1;
        if (rec.types[t] != null) rec.types[t] += 1;
        else rec.types.other = (rec.types.other || 0) + 1;
      }
      const f = n.file || '';
      if (f) {
        const L = extLang(f);
        if (L === 'py') rec.lang.py += 1;
        else if (L === 'ts') rec.lang.ts += 1;
        else rec.lang.other += 1;
      }
    });

    const dirEdges = new Map();
    function edgeKey(a, b) {
      return a < b ? `${a}\t${b}` : `${b}\t${a}`;
    }
    raw.links.forEach(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      const sn = nodeById.get(sid);
      const tn = nodeById.get(tid);
      if (!sn || !tn) return;
      const da = nodeDir(sn);
      const db = nodeDir(tn);
      if (!da && !db) return;
      if (da === db) return;
      const k = edgeKey(da || '_', db || '_');
      if (!dirEdges.has(k)) {
        dirEdges.set(k, { source: da || '_', target: db || '_', weight: 0, types: {} });
      }
      const e = dirEdges.get(k);
      e.weight += 1;
      const lt = l.type || 'CALLS';
      e.types[lt] = (e.types[lt] || 0) + 1;
    });

    const dirsSorted = [...dirMap.values()]
      .filter(d => d.childCount > 0)
      .sort((a, b) => b.childCount - a.childCount);

    const topDirs = dirsSorted.slice(0, MAX_GALAXY_DIRS);
    const visibleDirSet = new Set(topDirs.map(d => d.id));

    const galaxyNodes = topDirs.map(d => ({
      id: 'dir:' + d.id,
      kind: 'directory',
      dirId: d.id,
      name: d.name,
      label: d.name,
      childCount: d.childCount,
      types: { ...d.types },
      lang: { ...d.lang },
      color: directoryColor(d.lang),
      radius: 18 + Math.sqrt(d.childCount) * 1.2,
    }));

    const galaxyLinks = [];
    dirEdges.forEach(e => {
      if (!visibleDirSet.has(e.source) || !visibleDirSet.has(e.target)) return;
      if (e.source === e.target) return;
      galaxyLinks.push({
        source: 'dir:' + e.source,
        target: 'dir:' + e.target,
        weight: e.weight,
        type: Object.keys(e.types).sort((a, b) => (e.types[b] || 0) - (e.types[a] || 0))[0] || 'CALLS',
      });
    });

    const filesByDir = new Map();
    raw.nodes.forEach(n => {
      if (n.type !== 'file' || !n.file) return;
      const d = dirname(n.file);
      if (!filesByDir.has(d)) filesByDir.set(d, []);
      filesByDir.get(d).push(n);
    });

    const fileEdgesByDir = new Map();
    raw.links.forEach(l => {
      if (l.type !== 'IMPORTS') return;
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      const sn = nodeById.get(sid);
      const tn = nodeById.get(tid);
      if (!sn || !tn || !sn.file || !tn.file) return;
      const ds = dirname(sn.file);
      const dt = dirname(tn.file);
      if (ds !== dt) return;
      const fa = sn.file;
      const fb = tn.file;
      if (fa === fb) return;
      if (!fileEdgesByDir.has(ds)) fileEdgesByDir.set(ds, new Map());
      const m = fileEdgesByDir.get(ds);
      const fk = fa < fb ? `${fa}\t${fb}` : `${fb}\t${fa}`;
      if (!m.has(fk)) m.set(fk, { source: fa, target: fb, weight: 0, type: 'IMPORTS' });
      m.get(fk).weight += 1;
    });

    function symbolCountInFile(filePath) {
      let c = 0;
      raw.nodes.forEach(n => {
        if (n.file === filePath && (n.type === 'function' || n.type === 'method')) c += 1;
      });
      return c;
    }

    function buildStar(dirId) {
      let files = filesByDir.get(dirId) || [];
      if (files.length === 0) {
        const seen = new Set();
        raw.nodes.forEach(n => {
          if (!n.file || dirname(n.file) !== dirId) return;
          if (n.type === 'file') seen.add(n.file);
        });
        if (seen.size === 0) {
          raw.nodes.forEach(n => {
            if (!n.file || dirname(n.file) !== dirId) return;
            seen.add(n.file);
          });
        }
        files = [...seen].map(fp => ({
          id: 'vf:' + fp,
          name: basename(fp),
          type: 'file',
          file: fp,
          line: 0,
          val: 1,
        }));
      }
      const nodes = files.slice(0, MAX_STAR_FILES).map(f => {
        const fp = f.file || f.id;
        const sc = symbolCountInFile(fp) + 1;
        const col = extLang(fp) === 'py' ? COLORS.filePython : extLang(fp) === 'ts' ? COLORS.fileTS : COLORS.fileMixed;
        return {
          id: 'file:' + fp,
          kind: 'file',
          rawId: f.id,
          name: f.name || basename(fp),
          file: fp,
          color: col,
          radius: Math.max(12, 12 + Math.sqrt(sc) * 1.5),
        };
      });
      const fset = new Set(nodes.map(n => n.file));
      const linkMap = fileEdgesByDir.get(dirId) || new Map();
      const links = [];
      linkMap.forEach(e => {
        if (fset.has(e.source) && fset.has(e.target)) {
          links.push({
            source: 'file:' + e.source,
            target: 'file:' + e.target,
            weight: e.weight,
            type: 'IMPORTS',
          });
        }
      });
      return { nodes, links };
    }

    function buildPlanet(filePath, preferSymIds) {
      const prefer = Array.isArray(preferSymIds) ? preferSymIds.filter(Boolean) : [];
      const nodes = [];
      raw.nodes.forEach(n => {
        if (n.file !== filePath) return;
        if (n.type !== 'function' && n.type !== 'class' && n.type !== 'method') return;
        const isClass = n.type === 'class';
        const col = isClass ? COLORS.class : n.type === 'method' ? COLORS.method : COLORS.function;
        const baseR = isClass ? 14 : n.type === 'method' ? 11 : 10;
        nodes.push({
          id: 'sym:' + n.id,
          kind: isClass ? 'class' : 'function',
          symId: n.id,
          raw: n,
          name: n.name || n.id,
          color: col,
          radius: Math.max(10, baseR),
        });
      });
      nodes.sort((a, b) => (b.raw.val || 0) - (a.raw.val || 0) || (a.name || '').localeCompare(b.name || ''));
      const seen = new Set();
      const kept = [];
      prefer.forEach(pid => {
        const n = nodes.find(x => x.symId === pid);
        if (n && !seen.has(n.symId)) {
          kept.push(n);
          seen.add(n.symId);
        }
      });
      for (let i = 0; i < nodes.length && kept.length < MAX_PLANET_SYMBOLS; i++) {
        const n = nodes[i];
        if (!seen.has(n.symId)) {
          kept.push(n);
          seen.add(n.symId);
        }
      }
      const idset = new Set(kept.map(n => n.symId));
      const links = [];
      raw.links.forEach(l => {
        if (l.type !== 'CALLS') return;
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (!idset.has(sid) || !idset.has(tid)) return;
        links.push({
          source: 'sym:' + sid,
          target: 'sym:' + tid,
          weight: 1,
          type: 'CALLS',
        });
      });
      return { nodes: kept, links };
    }

    const dirFilesMap = {};
    raw.nodes.forEach(node => {
      if (node.type === 'file' && node.file) {
        const dir = dirname(node.file);
        if (!dirFilesMap[dir]) dirFilesMap[dir] = [];
        dirFilesMap[dir].push({
          name: basename(node.file),
          symbolCount: 0,
          id: node.id,
          type: (node.file || '').toLowerCase().endsWith('.py') ? 'python' : 'typescript',
        });
      }
    });
    raw.nodes.forEach(node => {
      const t = node.type || '';
      if (['function', 'class', 'method'].includes(t) && node.file) {
        const dir = dirname(node.file);
        const fileName = basename(node.file);
        const arr = dirFilesMap[dir];
        if (!arr) return;
        const fileEntry = arr.find(f => f.name === fileName);
        if (fileEntry) fileEntry.symbolCount += 1;
      }
    });
    Object.keys(dirFilesMap).forEach(dir => {
      dirFilesMap[dir].sort((a, b) => b.symbolCount - a.symbolCount);
    });

    const maxEdgeWeight = galaxyLinks.length ? Math.max(...galaxyLinks.map(e => e.weight || 1)) : 1;
    for (const node of galaxyNodes) {
      const nid = node.id;
      node.totalEdgeWeight = galaxyLinks
        .filter(e => e.source === nid || e.target === nid)
        .reduce((sum, e) => sum + (e.weight || 1), 0);
    }
    const maxNodeWeight = galaxyNodes.length ? Math.max(...galaxyNodes.map(n => n.totalEdgeWeight || 0), 1) : 1;

    return {
      raw,
      nodeById,
      galaxy: { nodes: galaxyNodes, links: galaxyLinks },
      maxEdgeWeight,
      maxNodeWeight,
      buildStar,
      buildPlanet,
      dirsSorted,
      dirFilesMap,
    };
  }

  /** --- Pixi + sim --- */
  let app = null;
  /** slice18a-lite.1: single white hex RenderTexture for all galaxy directory pool sprites */
  let galaxyDirectoryHexTexture = null;
  /** slice18a-lite.1: white radial-falloff glow RenderTexture for galaxy pool glow sprites */
  let galaxyDirectoryGlowTexture = null;
  let world = null;
  let layerEdges = null;
  /** Single batched Graphics for all galaxy-level directory edges (Physarum). */
  let galaxyEdgeGfx = null;
  let galaxyEdgeFrameCounter = -1;
  /** Low-end mobile iGPU: reduce fidelity; set false to restore richer visuals (heavier GPU). */
  const GPU_SAFE_MODE = true;
  const MAX_GALAXY_PHYSARUM_EDGES_PER_FRAME = 500;
  let layerNodes = null;
  let childrenGfx = null;
  let signalFlowGfx = null;
  let rippleGfx = null;
  /** Mycelium flow: fixed pool, galaxy view only (single batched Graphics). */
  const MYCELIUM_POOL_SIZE = 500;
  const MYCELIUM_TOP_EDGES = 50;
  const myceliumParticlePool = [];
  for (let _mi = 0; _mi < MYCELIUM_POOL_SIZE; _mi++) {
    myceliumParticlePool.push({
      edgeIndex: 0,
      t: 0,
      speed: 0.003,
      size: 1.5,
      alpha: 0.6,
      active: false,
      reverse: false,
    });
  }
  let galaxyLabelPool = [];
  /** Rebuilt each frame in galaxy gravitational hover (world-space hit targets for file orbit dots). */
  let visibleChildFiles = [];
  /** Sticky directory: keep orbit files visible while moving toward dots or during short grace period */
  let stickyDir = null;
  let stickyTimeout = null;
  let _gravScreenPt = null;
  let _physarumScreenPt = null;
  let bgGraphics = null;
  let starGraphics = null;
  let gridGraphics = null;
  let darkMatterGfx = null;
  let entanglementGfx = null;
  let darkMatterVisible = false;

  let timelineData = null;
  let timelineVisible = false;

  let model = null;
  let rawGraphData = null;
  let xrayOpen = false;
  let xrayDirId = null;
  /** @type {'module'|'function'} */
  let xrayViewKind = 'module';
  let planetCreateDelayed = null;
  let planetReverseActive = false;
  let starReverseActive = false;
  let viewLevel = 'galaxy';
  let selectedDir = null;
  /** @type {null | { name: string, dirId?: string, filePath?: string, symbolCount?: number, id?: string }} */
  let selectedFile = null;
  let starNodes = [];
  let planetNodes = [];
  let starViewTitle = null;
  let planetViewTitle = null;
  let symbolPopupEl = null;
  let currentNodes = [];
  let currentLinks = [];
  let simulation = null;
  let simNodes = [];
  let simLinks = [];
  let aiTraceActive = false;
  let aiTraceTarget = null;
  let aiTraceRunId = 0;

  const nodePool = [];
  /** AI trace: edge keys `idA\\0idB` (sorted) -> expiry timestamp (performance.now()). */
  const traceEdgePulseUntil = new Map();

  let worldScale = 1;
  let worldTx = 0;
  let worldTy = 0;
  let targetWorldScale = 1;
  let targetWorldTx = 0;
  let targetWorldTy = 0;

  let searchQuery = '';
  let searchMatches = [];
  let searchDebounceTimer = null;
  let hoveredSimNode = null;
  let activeTweens = [];
  let labelTop20Key = '';
  let labelTop20Set = null;

  function killTweens() {
    activeTweens.forEach(t => t.kill());
    activeTweens = [];
  }

  function resetGalaxyDrillState() {}

  function resolveDirFilePath(dirId, fileName) {
    const nodes = (rawGraphData && rawGraphData.nodes) || [];
    const hit = nodes.find(
      n => n.type === 'file' && n.file && dirname(n.file) === dirId && basename(n.file) === fileName
    );
    if (hit && hit.file) return hit.file;
    return dirId ? dirId + '/' + fileName : fileName;
  }

  function getSymbolsForFile(filePath, dirId) {
    const fileName = basename(filePath || '');
    const fullPath = filePath && filePath.includes('/')
      ? filePath
      : dirId
        ? dirId + '/' + fileName
        : fileName;
    const nodes = (rawGraphData && rawGraphData.nodes) || [];
    return nodes
      .filter(
        n =>
          ['function', 'class', 'method'].includes(n.type) &&
          n.file &&
          (n.file === fullPath ||
            n.file.endsWith('/' + fileName) ||
            (basename(n.file) === fileName && dirname(n.file) === dirId))
      )
      .map(n => ({
        id: n.id,
        name: n.name,
        type: n.type,
        line: n.line,
        complexity: n.val || 0,
      }))
      .sort((a, b) => (b.complexity || 0) - (a.complexity || 0))
      .slice(0, 100);
  }

  /** Route / validation / error / helper heuristics on symbol name (planet view). */
  function classifyFunction(sym) {
    const name = (sym && sym.name ? String(sym.name) : '').toLowerCase();
    if (
      name.includes('get_') ||
      name.includes('post_') ||
      name.includes('put_') ||
      name.includes('delete_') ||
      name.includes('patch_') ||
      name.startsWith('api_') ||
      name.includes('endpoint') ||
      name.includes('route') ||
      name.includes('handler') ||
      name.includes('view')
    ) {
      return { type: 'nucleus', color: 0x00e676, label: 'Handler' };
    }
    if (
      name.includes('valid') ||
      name.includes('check') ||
      name.includes('verify') ||
      name.includes('auth') ||
      name.includes('permission') ||
      name.includes('sanitize') ||
      name.includes('assert')
    ) {
      return { type: 'membrane', color: 0xff5252, label: 'Validator' };
    }
    if (
      name.includes('error') ||
      name.includes('exception') ||
      name.includes('cleanup') ||
      name.includes('dispose') ||
      name.includes('close') ||
      name.includes('shutdown') ||
      name.startsWith('_handle_error') ||
      name.includes('fallback')
    ) {
      return { type: 'lysosome', color: 0xb388ff, label: 'Error Handler' };
    }
    if (
      name.startsWith('_') ||
      name.includes('helper') ||
      name.includes('util') ||
      name.includes('format') ||
      name.includes('convert') ||
      name.includes('parse') ||
      name.includes('normalize') ||
      name.includes('transform')
    ) {
      return { type: 'ribosome', color: 0xffd740, label: 'Helper' };
    }
    return { type: 'mitochondria', color: 0x00e5ff, label: 'Logic' };
  }

  function classifyPlanetSymbol(sym) {
    if (sym.type === 'class') {
      return { type: 'class', color: 0xa855f7, label: 'Class' };
    }
    const c = classifyFunction(sym);
    if (sym.type === 'method') {
      return { type: c.type, color: c.color, label: 'Method · ' + c.label };
    }
    return c;
  }

  function edgeColor(linkType) {
    return LINK_HEX[linkType] || COLORS.edgeDefault;
  }

  function drawHexagon(g, r, fill, alpha, lineW, lineColor) {
    g.clear();
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i - Math.PI / 6;
      pts.push(Math.cos(a) * r, Math.sin(a) * r);
    }
    g.beginFill(fill, alpha);
    g.drawPolygon(pts);
    g.endFill();
    g.lineStyle(lineW, lineColor, 0.85);
    g.drawPolygon(pts);
  }

  function drawCircleNode(g, r, fill, alpha, ringColor) {
    g.clear();
    g.beginFill(fill, 0.12);
    g.drawCircle(0, 0, r * 2.4);
    g.endFill();
    g.lineStyle(2, ringColor, 0.9);
    g.drawCircle(0, 0, r);
    g.beginFill(fill, 0.35);
    g.drawCircle(0, 0, r * 0.92);
    g.endFill();
  }

  function drawDiamond(g, r, fill) {
    g.clear();
    g.beginFill(fill, 0.12);
    g.drawCircle(0, 0, r * 2.2);
    g.endFill();
    g.lineStyle(2, fill, 0.95);
    g.beginFill(fill, 0.4);
    g.drawPolygon([0, -r, r, 0, 0, r, -r, 0]);
    g.endFill();
  }

  function drawClassSquare(g, r, fill) {
    g.clear();
    g.beginFill(fill, 0.12);
    g.drawCircle(0, 0, r * 2.4);
    g.endFill();
    g.lineStyle(2, fill, 0.95);
    g.beginFill(fill, 0.38);
    g.drawRoundedRect(-r, -r, r * 2, r * 2, 4);
    g.endFill();
  }

  function acquireNodePool(i) {
    while (nodePool.length <= i) {
      const c = new PIXI.Container();
      const glow = new PIXI.Sprite(galaxyDirectoryGlowTexture);
      glow.anchor.set(0.5, 0.5);
      const shape = new PIXI.Sprite(galaxyDirectoryHexTexture);
      shape.anchor.set(0.5, 0.5);
      const label = new PIXI.Text('', {
        fontFamily: 'Outfit, system-ui, sans-serif',
        fontSize: 11,
        fill: 0xffffff,
        align: 'center',
      });
      label.anchor.set(0.5, 0);
      label.visible = false;
      c.addChild(glow);
      c.addChild(shape);
      c.addChild(label);
      c.eventMode = 'static';
      c.cursor = 'pointer';
      c.visible = false;
      c.on('pointerover', onNodeOver);
      c.on('pointerout', onNodeOut);
      c.on('pointerdown', onNodeRightDown);
      c.on('pointertap', onNodeClick);
      nodePool.push({ container: c, glow, shape, label, simNode: null });
      layerNodes.addChild(c);
    }
    return nodePool[i];
  }

  function clientFromPixiEvent(e) {
    const o = e.data && e.data.originalEvent;
    if (o && o.clientX != null) return { x: o.clientX, y: o.clientY };
    const br = app.view.getBoundingClientRect();
    return { x: br.left + e.global.x, y: br.top + e.global.y };
  }

  function onNodeOver(e) {
    const c = e.currentTarget;
    const entry = nodePool.find(p => p.container === c);
    if (!entry || !entry.simNode) return;
    hoveredSimNode = entry.simNode;
    const sn = entry.simNode;
    const gravGalaxyDir = viewLevel === 'galaxy' && sn.kind === 'directory';
    if (!gravGalaxyDir) {
      gsap.to(c.scale, { x: 1.3, y: 1.3, duration: 0.2, ease: 'back.out(1.7)' });
    }
    // Glow appearance: redrawNodeGlow + syncPixiFromSim (pool glow is Sprite; no Graphics draw here)
    const pt = clientFromPixiEvent(e);
    showTooltip(sn, pt.x, pt.y);
    if (!(viewLevel === 'galaxy' && sn.kind === 'directory')) {
      pulseNeighbors(sn);
    }
    syncPixiFromSim();
  }

  function onNodeOut(e) {
    const c = e.currentTarget;
    const entry = nodePool.find(p => p.container === c);
    const snOut = entry && entry.simNode;
    hoveredSimNode = null;
    hideTooltip();
    const gravGalaxyDir = viewLevel === 'galaxy' && snOut && snOut.kind === 'directory';
    if (!gravGalaxyDir) {
      gsap.to(c.scale, { x: 1, y: 1, duration: 0.18, ease: 'power2.out' });
    }
    if (entry && entry.simNode) redrawNodeGlow(entry, entry.simNode, false);
    clearNeighborPulse();
    syncPixiFromSim();
  }

  function redrawNodeGlow(entry, sn, isHover) {
    const g = entry.glow;
    let a = isHover ? 0.4 : 0.15;
    if (!isHover && viewLevel === 'galaxy' && sn.kind === 'directory' && model) {
      const nodeWeight = sn.totalEdgeWeight || 0;
      const maxNodeWeight = model.maxNodeWeight || 100;
      a = 0.1 + Math.min(nodeWeight / maxNodeWeight, 1) * 0.25;
    }
    if (g instanceof PIXI.Sprite) {
      g.tint = sn.color;
      g._glowBaseAlpha = a;
      const rWorld = (sn.radius || 12) * 2.5;
      g.scale.set(rWorld / GLOW_TEXTURE_BASE_RADIUS);
      g.alpha = a;
      return;
    }
    g.clear();
    g.beginFill(sn.color, a);
    g.drawCircle(0, 0, (sn.radius || 12) * 2.5);
    g.endFill();
  }

  let neighborPulseTweens = [];
  function clearNeighborPulse() {
    neighborPulseTweens.forEach(t => t.kill());
    neighborPulseTweens = [];
    nodePool.forEach(p => {
      if (!p.simNode || !p.container.visible) return;
      const sn = p.simNode;
      const dim = searchQuery && !nodeMatchesSearch(sn) ? 0.25 : 1;
      gsap.to(p.container, { alpha: dim, duration: 0.15 });
    });
  }

  function pulseNeighbors(center) {
    clearNeighborPulse();
    const id = center.id;
    const nbr = new Set();
    currentLinks.forEach(l => {
      const s = l.source.id || l.source;
      const t = l.target.id || l.target;
      if (s === id) nbr.add(t);
      if (t === id) nbr.add(s);
    });
    nodePool.forEach(p => {
      if (!p.simNode || !nbr.has(p.simNode.id)) return;
      const tw = gsap.to(p.container.scale, {
        x: 1.15,
        y: 1.15,
        duration: 0.2,
        yoyo: true,
        repeat: 1,
        ease: 'sine.inOut',
      });
      neighborPulseTweens.push(tw);
    });
  }

  function pointerEventButton(e) {
    const oe = e.data && e.data.originalEvent;
    if (oe && typeof oe.button === 'number') return oe.button;
    if (typeof e.button === 'number') return e.button;
    return 0;
  }

  function normalizeFsPath(p) {
    return String(p || '').replace(/\\/g, '/');
  }

  /** Slice 17c — Pixi drill updates the same scope channel as React (studioScopeStore). */
  function notifyViewerScope(payload) {
    try {
      const pathLogged =
        payload && payload.kind === 'repo'
          ? ''
          : payload && payload.path != null
            ? String(payload.path)
            : '';
      console.debug('[slice17c1] notifyViewerScope', {
        kind: payload && payload.kind ? payload.kind : '?',
        path: pathLogged,
      });
      if (studio._options && typeof studio._options.onViewerScope === 'function') {
        studio._options.onViewerScope(payload);
      }
    } catch (_e) { /* callback guard */ }
  }

  function notifyScopeVisualEmpty(detail) {
    try {
      if (studio._options && typeof studio._options.onScopeVisualEmpty === 'function') {
        studio._options.onScopeVisualEmpty(detail);
      }
    } catch (_e) { /* callback guard */ }
  }

  function onNodeRightDown(e) {
    if (pointerEventButton(e) !== 2) return;
    e.stopPropagation();
    const oe = e.data && e.data.originalEvent;
    if (oe && oe.preventDefault) oe.preventDefault();
    const entry = nodePool.find(p => p.container === e.currentTarget);
    if (!entry || !entry.simNode) return;
    const sn = entry.simNode;
    if (viewLevel !== 'galaxy' || sn.kind !== 'directory') return;
    let did = sn.dirId;
    if (did === undefined || did === null) did = sn.raw && sn.raw.id;
    if (did === undefined || did === null) return;
    if (xrayOpen && xrayDirId === did) closeXray();
    else void openXray(sn);
  }

  function onNodeClick(e) {
    e.stopPropagation();
    if (pointerEventButton(e) === 2) return;
    const entry = nodePool.find(p => p.container === e.currentTarget);
    if (!entry || !entry.simNode) return;
    const sn = entry.simNode;
    if (viewLevel === 'galaxy' && sn.kind === 'directory') {
      let did = sn.dirId;
      if (did === undefined || did === null) did = sn.raw && sn.raw.id;
      if (did === undefined || did === null) return;
      // slice17c1 probes A–C — galaxy drill is synchronous via transitionToStar (R0).
      console.debug('[slice17c1] click', {
        kind: 'galaxy',
        path: String(did),
        timestamp: typeof performance !== 'undefined' ? performance.now() : Date.now(),
      });
      try {
        if (typeof studio._options.onFileOrDirClick === 'function') {
          studio._options.onFileOrDirClick(String(did));
        }
      } catch (_e) { /* callback only */ }
      if (xrayOpen) closeXray();
      hideSymbolPopup();
      console.debug('[slice17c1] calling transitionToStar', { dirId: String(did) });
      transitionToStar(did, sn);
      console.debug('[slice17c1] transitionToStar returned', { success: true });
    }
  }

  function showTooltip(sn, gx, gy) {
    const el = document.getElementById('tooltip');
    const raw = sn.raw;
    el.querySelector('.tooltip-name').textContent = sn.name || sn.id;
    const typeEl = el.querySelector('.tooltip-type');
    const typ = raw ? raw.type : sn.kind;
    typeEl.textContent = typ || '';
    typeEl.style.background = 'rgba(99,102,241,0.2)';
    typeEl.style.color = '#a5b4fc';
    typeEl.style.border = '1px solid rgba(99,102,241,0.35)';
    let fileLine = raw ? (raw.file || '') : (sn.file || sn.dirId || '');
    if (sn.kind === 'directory') {
      fileLine = (sn.dirId || '') + ' · ' + (sn.childCount || 0) + ' symbols';
    }
    el.querySelector('.tooltip-file').textContent = fileLine;
    const line = raw && raw.line != null ? 'Line ' + raw.line : '';
    const comp = raw && raw.val != null ? 'Complexity ' + raw.val : '';
    el.querySelector('.tooltip-lines').textContent = [line, comp].filter(Boolean).join(' · ');
    el.style.display = 'block';
    el.style.left = Math.min(gx + 14, window.innerWidth - 400) + 'px';
    el.style.top = Math.min(gy + 14, window.innerHeight - 140) + 'px';
  }

  function hideTooltip() {
    document.getElementById('tooltip').style.display = 'none';
  }

  function fitWorldToNodes(animate) {
    if (viewLevel !== 'galaxy' || !simNodes.length || !app) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const labelPadWorld = 0;
    simNodes.forEach(n => {
      const r = n.radius || 12;
      minX = Math.min(minX, n.x - r);
      maxX = Math.max(maxX, n.x + r);
      minY = Math.min(minY, n.y - r);
      maxY = Math.max(maxY, n.y + r + labelPadWorld);
    });
    const bw = maxX - minX || 1;
    const bh = maxY - minY || 1;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const pad = 0.85;
    const sx = (app.screen.width * pad) / bw;
    const sy = (app.screen.height * pad) / bh;
    let s = Math.min(sx, sy);
    s = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, s));
    targetWorldScale = s;
    targetWorldTx = app.screen.width / 2 - cx * s;
    targetWorldTy = app.screen.height / 2 - cy * s;
    if (animate === false) {
      world.scale.set(s);
      world.position.set(targetWorldTx, targetWorldTy);
      worldScale = s;
      worldTx = targetWorldTx;
      worldTy = targetWorldTy;
      return;
    }
    smoothWorld(0.6, 'power3.out');
  }

  function smoothWorld(dur, ease) {
    killTweens();
    const from = {
      s: world.scale.x,
      x: world.position.x,
      y: world.position.y,
    };
    const tw = gsap.to(from, {
      s: targetWorldScale,
      x: targetWorldTx,
      y: targetWorldTy,
      duration: dur,
      ease: ease || 'power3.out',
      onUpdate: () => {
        world.scale.set(from.s);
        world.position.set(from.x, from.y);
        worldScale = from.s;
        worldTx = from.x;
        worldTy = from.y;
      },
    });
    activeTweens.push(tw);
  }

  const SUBVIEW_SIGNAL_MAX = 30;
  const STAR_VIEW_MAX_FILES = 150;
  const STAR_GROWTH_MAX_ANIM = 50;
  const STAR_GROWTH_TOTAL_SEC = 0.8;
  const STAR_MIGRATE_SEC = 0.4;
  const STAR_DEPTH_STAGGER_SEC = 0.15;
  const STAR_DRILL_CREATE_DELAY_SEC = 0.2;

  function easeBackOut(t) {
    const s = 1.70158;
    return 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2);
  }

  function starGrowthSeed(dirId) {
    let h = 2166136261;
    const s = String(dirId || '');
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function starGrowthRng(seed) {
    let state = seed >>> 0;
    return function () {
      state = (state + 0x6d2b79f5) | 0;
      let t = Math.imul(state ^ (state >>> 15), state | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function starGrowthNeighbors(current, links, idSet, visited) {
    const out = [];
    const seen = new Set();
    for (let li = 0; li < links.length; li++) {
      const l = links[li];
      const s = l.source;
      const t = l.target;
      if (!s || !t) continue;
      const sid = s.growthId;
      const tid = t.growthId;
      if (sid == null || tid == null) continue;
      if (sid === current && idSet.has(tid) && !visited.has(tid)) {
        if (!seen.has(tid)) {
          seen.add(tid);
          out.push(tid);
        }
      } else if (tid === current && idSet.has(sid) && !visited.has(sid)) {
        if (!seen.has(sid)) {
          seen.add(sid);
          out.push(sid);
        }
      }
    }
    return out;
  }

  function computeStarGrowthTree(nodes, links) {
    if (!nodes.length) return null;
    const idSet = new Set(nodes.map(n => n.growthId));
    const root = nodes.reduce((a, b) => ((a.connections || 0) > (b.connections || 0) ? a : b));
    const rootId = root.growthId;
    const tree = { root, rootId, children: {}, depth: {}, parent: {}, edges: [] };
    const queue = [rootId];
    tree.depth[rootId] = 0;
    const visited = new Set([rootId]);
    while (queue.length) {
      const current = queue.shift();
      const neighbors = starGrowthNeighbors(current, links, idSet, visited);
      tree.children[current] = neighbors;
      for (let ni = 0; ni < neighbors.length; ni++) {
        const nid = neighbors[ni];
        visited.add(nid);
        tree.depth[nid] = tree.depth[current] + 1;
        tree.parent[nid] = current;
        tree.edges.push({ parent: current, child: nid });
        queue.push(nid);
      }
    }
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      const id = n.growthId;
      if (!visited.has(id)) {
        if (!tree.children[rootId]) tree.children[rootId] = [];
        tree.children[rootId].push(id);
        tree.depth[id] = (tree.depth[rootId] || 0) + 1;
        tree.parent[id] = rootId;
        tree.edges.push({ parent: rootId, child: id });
        visited.add(id);
      }
    }
    return tree;
  }

  function computeStarGrowthPositions(tree, centerX, centerY, rand) {
    const positions = {};
    const angleSpread = Math.PI * 0.6;
    const branchLength = 80;
    const rootId = tree.rootId;
    positions[rootId] = { x: centerX, y: centerY, angle: -Math.PI / 2 };

    const parentIds = Object.keys(tree.children);
    for (let pi = 0; pi < parentIds.length; pi++) {
      const parentId = parentIds[pi];
      const childIds = tree.children[parentId];
      if (!childIds || !childIds.length) continue;
      const parentPos = positions[parentId];
      if (!parentPos) continue;
      const baseAngle = parentPos.angle;
      const step = angleSpread / (childIds.length + 1);
      for (let i = 0; i < childIds.length; i++) {
        const childId = childIds[i];
        const angle = baseAngle - angleSpread / 2 + step * (i + 1);
        const jitterAngle = angle + (rand() - 0.5) * ((5 * Math.PI) / 180);
        const depth = tree.depth[childId] || 1;
        const decay = Math.pow(0.75, depth);
        const jitterLen = branchLength * (0.85 + rand() * 0.3);
        positions[childId] = {
          x: parentPos.x + Math.cos(jitterAngle) * jitterLen * decay,
          y: parentPos.y + Math.sin(jitterAngle) * jitterLen * decay,
          angle: jitterAngle,
        };
      }
    }
    return positions;
  }

  function relaxStarGrowthCollisions(positions, growthIdToNode, minGap) {
    const ids = Object.keys(positions);
    for (let pass = 0; pass < 8; pass++) {
      for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
          const a = positions[ids[i]];
          const b = positions[ids[j]];
          const na = growthIdToNode.get(ids[i]);
          const nb = growthIdToNode.get(ids[j]);
          const ra = (na && na.radius) || 12;
          const rb = (nb && nb.radius) || 12;
          const need = minGap + ra + rb;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const d = Math.hypot(dx, dy) || 1e-6;
          if (d < need) {
            const push = (need - d) * 0.5;
            const ux = (dx / d) * push;
            const uy = (dy / d) * push;
            a.x -= ux;
            a.y -= uy;
            b.x += ux;
            b.y += uy;
          }
        }
      }
    }
  }

  function drawStarGrowthEdges(growthGfx, sc) {
    if (!growthGfx || !sc || !sc._growthTree) return;
    growthGfx.clear();
    const tree = sc._growthTree;
    const edges = tree.edges;
    if (!edges || !edges.length) {
      growthGfx.lineStyle(0);
      return;
    }
    const byId = sc._growthIdToNode;
    if (!byId) {
      growthGfx.lineStyle(0);
      return;
    }
    for (let ei = 0; ei < edges.length; ei++) {
      const e = edges[ei];
      const pNode = byId.get(e.parent);
      const cNode = byId.get(e.child);
      if (!pNode || !cNode) continue;
      const pu = pNode._growEdgeU != null ? pNode._growEdgeU : 1;
      const cu = cNode._growEdgeU != null ? cNode._growEdgeU : 0;
      const t = Math.min(pu, cu);
      if (t <= 0.001) continue;
      const sx = pNode.x;
      const sy = pNode.y;
      const ex = sx + (cNode.x - sx) * t;
      const ey = sy + (cNode.y - sy) * t;
      const col = cNode.color != null ? cNode.color : 0x3b82f6;
      growthGfx.lineStyle(1, col, 0.45);
      growthGfx.moveTo(sx, sy);
      growthGfx.lineTo(ex, ey);
    }
    growthGfx.lineStyle(0);
  }

  /** Edges between files in a directory for star-view force + rendering (deduped). */
  function buildStarEdgeList(dirId, starNodes) {
    const edges = [];
    if (!rawGraphData || !rawGraphData.links || !starNodes.length) return edges;

    const fileNames = starNodes.map(sn => (sn.fileData && sn.fileData.name) || '');
    const filePaths = starNodes.map((sn, i) => {
      const fd = sn.fileData;
      if (!fd) return fileNames[i] || '';
      return fd.filePath || fd.id || fd.name || fileNames[i] || '';
    });
    const seen = new Set();

    for (const link of rawGraphData.links) {
      const lt = link.type || '';
      if (lt === 'DEFINES' || lt === 'CONTAINS') continue;

      const srcRaw = link.source;
      const tgtRaw = link.target;
      const src =
        typeof srcRaw === 'string'
          ? srcRaw
          : srcRaw && typeof srcRaw.id === 'string'
            ? srcRaw.id
            : '';
      const tgt =
        typeof tgtRaw === 'string'
          ? tgtRaw
          : tgtRaw && typeof tgtRaw.id === 'string'
            ? tgtRaw.id
            : '';

      let srcIdx = -1;
      let tgtIdx = -1;

      for (let i = 0; i < filePaths.length; i++) {
        const fp = filePaths[i];
        const fn = fileNames[i];
        if (!fp && !fn) continue;
        const srcBase = src.split('::')[0] || src;
        if (
          (fp && (src.includes(fp) || src.includes(fn))) ||
          (fn && src.includes(fn)) ||
          (fp && srcBase && fp.includes(srcBase))
        ) {
          srcIdx = i;
        }
        const tgtBase = tgt.split('::')[0] || tgt;
        if (
          (fp && (tgt.includes(fp) || tgt.includes(fn))) ||
          (fn && tgt.includes(fn)) ||
          (fp && tgtBase && fp.includes(tgtBase))
        ) {
          tgtIdx = i;
        }
      }

      if (srcIdx < 0 && dirId && src && src.startsWith(dirId)) {
        const srcFile = src.split('/').pop().split('::')[0];
        srcIdx = fileNames.indexOf(srcFile);
        if (srcIdx < 0) {
          for (let i = 0; i < fileNames.length; i++) {
            const nm = fileNames[i];
            const stem = nm.replace(/\.[^.]+$/, '');
            if (
              srcFile === nm ||
              nm.includes(srcFile) ||
              srcFile.includes(stem)
            ) {
              srcIdx = i;
              break;
            }
          }
        }
      }
      if (tgtIdx < 0 && dirId && tgt && tgt.startsWith(dirId)) {
        const tgtFile = tgt.split('/').pop().split('::')[0];
        tgtIdx = fileNames.indexOf(tgtFile);
        if (tgtIdx < 0) {
          for (let i = 0; i < fileNames.length; i++) {
            const nm = fileNames[i];
            const stem = nm.replace(/\.[^.]+$/, '');
            if (
              tgtFile === nm ||
              nm.includes(tgtFile) ||
              tgtFile.includes(stem)
            ) {
              tgtIdx = i;
              break;
            }
          }
        }
      }

      if (model && model.nodeById) {
        const sid = typeof link.source === 'object' && link.source ? link.source.id : link.source;
        const tid = typeof link.target === 'object' && link.target ? link.target.id : link.target;
        const sn = sid ? model.nodeById.get(sid) : null;
        const tn = tid ? model.nodeById.get(tid) : null;
        if (sn && sn.file && dirname(sn.file) === dirId && sn.type === 'file') {
          const bf = basename(sn.file);
          const ix = fileNames.indexOf(bf);
          if (ix >= 0) srcIdx = ix;
        }
        if (tn && tn.file && dirname(tn.file) === dirId && tn.type === 'file') {
          const bf = basename(tn.file);
          const ix = fileNames.indexOf(bf);
          if (ix >= 0) tgtIdx = ix;
        }
      }

      if (srcIdx >= 0 && tgtIdx >= 0 && srcIdx !== tgtIdx) {
        const s = starNodes[srcIdx];
        const t = starNodes[tgtIdx];
        if (!s || !t) continue;

        const key = Math.min(srcIdx, tgtIdx) + ':' + Math.max(srcIdx, tgtIdx);
        if (seen.has(key)) continue;
        seen.add(key);

        const edgeColor =
          lt === 'ENTANGLED'
            ? 0xf59e0b
            : lt === 'DARK_FORCE'
              ? 0x8b5cf6
              : lt === 'CALLS'
                ? 0x4ade80
                : LINK_HEX[lt] || 0x3b82f6;

        edges.push({
          source: s,
          target: t,
          type: lt,
          color: edgeColor,
          _curveOffset: (Math.random() - 0.5) * 40,
        });
      }
    }

    return edges;
  }

  /** CALLS edges within one file for planet-view force + rendering (deduped). */
  function buildPlanetEdgeList(filePath, symbols, planetNodes) {
    const edges = [];
    if (!rawGraphData || !rawGraphData.links || !planetNodes.length) return edges;

    const symNames = symbols.map(s => s.name || '');
    const idSet = new Set(symbols.map(s => s.id).filter(Boolean));
    const seen = new Set();
    const links = rawGraphData.links || [];

    for (const link of links) {
      if (link.type !== 'CALLS') continue;

      const sid =
        typeof link.source === 'object' && link.source ? link.source.id : link.source;
      const tid =
        typeof link.target === 'object' && link.target ? link.target.id : link.target;
      let srcIdx = -1;
      let tgtIdx = -1;

      const srcStr =
        typeof link.source === 'string'
          ? link.source
          : link.source && link.source.id
            ? link.source.id
            : String(sid || '');
      const tgtStr =
        typeof link.target === 'string'
          ? link.target
          : link.target && link.target.id
            ? link.target.id
            : String(tid || '');

      for (let i = 0; i < symNames.length; i++) {
        const nm = symNames[i];
        if (srcStr.endsWith('::' + nm) || (nm && srcStr.includes(nm))) srcIdx = i;
        if (tgtStr.endsWith('::' + nm) || (nm && tgtStr.includes(nm))) tgtIdx = i;
      }

      if (srcIdx < 0 && sid && idSet.has(sid) && model && model.nodeById) {
        const sNode = model.nodeById.get(sid);
        if (sNode && sNode.file === filePath) {
          const ix = symbols.findIndex(s => s.id === sid);
          if (ix >= 0) srcIdx = ix;
        }
      }
      if (tgtIdx < 0 && tid && idSet.has(tid) && model && model.nodeById) {
        const tNode = model.nodeById.get(tid);
        if (tNode && tNode.file === filePath) {
          const ix = symbols.findIndex(s => s.id === tid);
          if (ix >= 0) tgtIdx = ix;
        }
      }

      if (srcIdx >= 0 && tgtIdx >= 0 && srcIdx !== tgtIdx) {
        const s = planetNodes[srcIdx];
        const t = planetNodes[tgtIdx];
        if (!s || !t) continue;

        const key = Math.min(srcIdx, tgtIdx) + ':' + Math.max(srcIdx, tgtIdx);
        if (seen.has(key)) continue;
        seen.add(key);

        edges.push({
          source: s,
          target: t,
          type: 'CALLS',
          color: 0x4ade80,
          _curveOffset: (Math.random() - 0.5) * 36,
        });
      }
    }

    return edges;
  }

  function cleanupStarView() {
    starViewTitle = null;
    const toRemove = [];
    for (let i = 0; i < world.children.length; i++) {
      const ch = world.children[i];
      if (ch._omnixType === 'star') toRemove.push(ch);
    }
    for (let j = 0; j < toRemove.length; j++) {
      const ch = toRemove[j];
      if (ch._growthTl) {
        ch._growthTl.kill();
        ch._growthTl = null;
      }
      if (ch._sim) {
        ch._sim.stop();
        ch._sim = null;
      }
      world.removeChild(ch);
      ch.destroy({ children: true });
    }
    starNodes = [];
  }

  function cleanupPlanetView() {
    studio?.setViewContext?.('non-planet');
    planetViewTitle = null;
    const toRemove = [];
    for (let i = 0; i < world.children.length; i++) {
      const ch = world.children[i];
      if (ch._omnixType === 'planet') toRemove.push(ch);
    }
    for (let j = 0; j < toRemove.length; j++) {
      const ch = toRemove[j];
      if (ch._nodes && Array.isArray(ch._nodes)) {
        for (let ni = 0; ni < ch._nodes.length; ni++) {
          const pn = ch._nodes[ni];
          if (pn && pn.container) {
            if (pn.container._omnixBornTween) {
              try {
                pn.container._omnixBornTween.kill();
              } catch (_e) { /* */ }
              delete pn.container._omnixBornTween;
            }
            gsap.killTweensOf(pn.container);
            gsap.killTweensOf(pn.container.scale);
          }
        }
      }
      if (ch._sim) {
        ch._sim.stop();
        ch._sim = null;
      }
      world.removeChild(ch);
      ch.destroy({ children: true });
    }
    planetNodes = [];
  }

  function restoreGalaxyView() {
    killTweens();
    gsap.killTweensOf(layerEdges);
    layerEdges.alpha = 1;
    nodePool.forEach(p => {
      if (!p || !p.container) return;
      gsap.killTweensOf(p.container);
      gsap.killTweensOf(p.container.scale);
      p.container.alpha = searchQuery && p.simNode && !nodeMatchesSearch(p.simNode) ? 0.25 : 1;
      p.container.scale.set(1);
    });
    fitWorldToNodes(false);
    syncPixiFromSim();
    updateBreadcrumb();
  }

  function restoreStarView() {
    hideSymbolPopup();
    for (let i = 0; i < starNodes.length; i++) {
      const sn = starNodes[i];
      if (!sn || !sn.container) continue;
      gsap.killTweensOf(sn.container);
      gsap.killTweensOf(sn.container.scale);
      sn._hover = false;
      sn.container.position.set(sn.x, sn.y);
      gsap.to(sn.container, {
        alpha: 1,
        duration: 0.35,
        ease: 'power2.out',
      });
      gsap.to(sn.container.scale, { x: 1, y: 1, duration: 0.25 });
    }
    selectedFile = null;
    const sc = world && world.children && world.children.find(c => c._omnixType === 'star');
    if (sc && sc._sim) sc._sim.alpha(0.45).restart();
    updateBreadcrumb();
  }

  function createStarView(dirId, files) {
    viewLevel = 'star';
    selectedDir = dirId;
    notifyViewerScope({ kind: 'directory', path: normalizeFsPath(dirId) });
    updateBreadcrumb();
    cleanupStarView();
    if (!world || !app) return;
    const starContainer = new PIXI.Container();
    starContainer.eventMode = 'passive';
    starContainer._omnixType = 'star';
    world.addChild(starContainer);

    gsap.to(world, { x: 0, y: 0, duration: 0.3, ease: 'power2.inOut' });
    gsap.to(world.scale, { x: 1, y: 1, duration: 0.3, ease: 'power2.inOut' });
    worldScale = 1;
    worldTx = 0;
    worldTy = 0;
    targetWorldScale = 1;
    targetWorldTx = 0;
    targetWorldTy = 0;

    const centerX = app.screen.width / 2;
    const centerY = app.screen.height / 2;
    const maxFilesAll = Math.min(files.length, STAR_VIEW_MAX_FILES);
    const fileSlice = files.slice(0, maxFilesAll);
    if (!fileSlice.length) {
      notifyScopeVisualEmpty({
        scopePath: normalizeFsPath(dirId),
        viewLevel: 'star',
      });
    } else {
      notifyScopeVisualEmpty(null);
    }
    const rand = starGrowthRng(starGrowthSeed(dirId));

    const starEdgeGfx = new PIXI.Graphics();
    starEdgeGfx.eventMode = 'none';
    starEdgeGfx.alpha = 0;
    starContainer.addChild(starEdgeGfx);

    const starGrowthGfx = new PIXI.Graphics();
    starGrowthGfx.eventMode = 'none';
    starGrowthGfx.alpha = 1;
    starContainer.addChild(starGrowthGfx);

    const starSignalGfx = new PIXI.Graphics();
    starSignalGfx.eventMode = 'none';
    starSignalGfx.alpha = 0;
    starContainer.addChild(starSignalGfx);

    starNodes = [];

    for (let i = 0; i < maxFilesAll; i++) {
      const file = fileSlice[i];
      const radius = 12 + Math.min((file.symbolCount || 0) / 3, 25);
      const nm = file.name || '';
      const color =
        nm.endsWith('.py')
          ? 0x3b82f6
          : nm.endsWith('.ts') || nm.endsWith('.tsx')
            ? 0x06b6d4
            : nm.endsWith('.js') || nm.endsWith('.jsx')
              ? 0x22d3ee
              : extLang(nm) === 'py'
                ? 0x3b82f6
                : extLang(nm) === 'ts'
                  ? 0x06b6d4
                  : 0x4ade80;

      const fileData = Object.assign({}, file, {
        dirId,
        filePath: resolveDirFilePath(dirId, file.name),
      });

      const growthId = fileData.filePath || dirId + '/' + (file.name || String(i));

      const fileContainer = new PIXI.Container();
      fileContainer.position.set(centerX, centerY);
      fileContainer.alpha = 0;
      fileContainer.scale.set(0.01, 0.01);
      fileContainer.eventMode = 'static';
      fileContainer.cursor = 'pointer';

      const glow = new PIXI.Graphics();
      glow.beginFill(color, 0.12);
      glow.drawCircle(0, 0, radius * 2.5);
      glow.endFill();
      glow.alpha = 0.55;
      fileContainer.addChild(glow);

      const circle = new PIXI.Graphics();
      circle.beginFill(color, 0.85);
      circle.drawCircle(0, 0, radius);
      circle.endFill();
      circle.lineStyle(1, 0xffffff, 0.25);
      circle.drawCircle(0, 0, radius);
      fileContainer.addChild(circle);

      const fn = nm.length > 18 ? nm.slice(0, 16) + '…' : nm;
      const label = new PIXI.Text(fn + '\n(' + (file.symbolCount || 0) + ')', {
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        fill: 0xe2e8f0,
        align: 'center',
      });
      label.anchor.set(0.5, 0);
      label.position.set(0, radius + 6);
      label.eventMode = 'none';
      fileContainer.addChild(label);

      const hitR = Math.max(radius * 2.5, radius + 48);
      fileContainer.hitArea = new PIXI.Circle(0, 0, hitR);

      starContainer.addChild(fileContainer);

      const snRef = {
        container: fileContainer,
        fileData,
        growthId,
        x: centerX,
        y: centerY,
        vx: 0,
        vy: 0,
        radius,
        color,
        glow,
        index: i,
        connections: 0,
        _hover: false,
        _growEdgeU: 0,
      };

      fileContainer.on('pointerdown', e => {
        const btn = pointerEventButton(e);
        if (btn === 2) {
          e.stopPropagation();
          const oe = e.data && e.data.originalEvent;
          if (oe && oe.preventDefault) oe.preventDefault();
          openXrayForDir(dirId);
          return;
        }
        if (btn !== 0) return;
        e.stopPropagation();
        try {
          if (typeof studio._options.onFileOrDirClick === 'function' && fileData && fileData.filePath) {
            studio._options.onFileOrDirClick(String(fileData.filePath));
          }
        } catch (_e) { /* */ }
        hideSymbolPopup();
        transitionToPlanet(fileData);
      });
      fileContainer.on('pointerover', () => {
        snRef._hover = true;
        gsap.to(fileContainer.scale, { x: 1.25, y: 1.25, duration: 0.2 });
      });
      fileContainer.on('pointerout', () => {
        snRef._hover = false;
        gsap.to(fileContainer.scale, { x: 1, y: 1, duration: 0.2 });
      });

      starNodes.push(snRef);
    }

    const starEdges = buildStarEdgeList(dirId, starNodes);

    const conn = starNodes.map(() => 0);
    for (let ei = 0; ei < starEdges.length; ei++) {
      const e = starEdges[ei];
      const si = e.source && e.source.index;
      const ti = e.target && e.target.index;
      if (si != null && conn[si] != null) conn[si]++;
      if (ti != null && conn[ti] != null) conn[ti]++;
    }
    for (let ci = 0; ci < starNodes.length; ci++) {
      starNodes[ci].connections = conn[ci] || 0;
    }

    const sortedIdx = starNodes.map((_, idx) => idx).sort((a, b) => conn[b] - conn[a]);
    const animIndexSet = new Set(sortedIdx.slice(0, Math.min(STAR_GROWTH_MAX_ANIM, sortedIdx.length)));
    const growthIdAnimSet = new Set();
    animIndexSet.forEach(idx => {
      growthIdAnimSet.add(starNodes[idx].growthId);
    });

    const animNodes = starNodes.filter((_, idx) => animIndexSet.has(idx));
    const subLinks = starEdges.filter(
      e =>
        e.source &&
        e.target &&
        growthIdAnimSet.has(e.source.growthId) &&
        growthIdAnimSet.has(e.target.growthId)
    );

    const growthTree = animNodes.length ? computeStarGrowthTree(animNodes, subLinks) : null;
    const growthPositions = growthTree
      ? computeStarGrowthPositions(growthTree, centerX, centerY, rand)
      : {};
    const growthIdToNode = new Map(starNodes.map(sn => [sn.growthId, sn]));
    if (growthTree && Object.keys(growthPositions).length) {
      relaxStarGrowthCollisions(growthPositions, growthIdToNode, 14);
    }

    function bfsStarGrowthOrder(tree, byGrowthId) {
      const order = [];
      if (!tree) return order;
      const q = [tree.rootId];
      const seen = new Set(q);
      while (q.length) {
        const id = q.shift();
        const node = byGrowthId.get(id);
        if (node) order.push(node);
        const ch = (tree.children[id] || []).slice();
        ch.sort(
          (a, b) =>
            (byGrowthId.get(b).connections || 0) - (byGrowthId.get(a).connections || 0)
        );
        for (let ci = 0; ci < ch.length; ci++) {
          const cid = ch[ci];
          if (!seen.has(cid)) {
            seen.add(cid);
            q.push(cid);
          }
        }
      }
      return order;
    }

    const bfsOrder = bfsStarGrowthOrder(growthTree, growthIdToNode);
    const depthMap = new Map();
    if (growthTree) {
      for (const id of Object.keys(growthTree.depth)) {
        depthMap.set(id, growthTree.depth[id]);
      }
    }

    const starSim = d3
      .forceSimulation(starNodes)
      .force('center', d3.forceCenter(centerX, centerY))
      .force('charge', d3.forceManyBody().strength(-80))
      .force('collision', d3.forceCollide().radius(d => d.radius * 2 + 10))
      .force('link', d3.forceLink(starEdges).distance(120).strength(0.3))
      .force('x', d3.forceX(centerX).strength(0.05))
      .force('y', d3.forceY(centerY).strength(0.05))
      .alphaDecay(0.02)
      .on('tick', () => {
        if (starContainer._growthPhaseComplete) {
          for (const sn of starNodes) {
            sn.container.position.set(sn.x, sn.y);
          }
        }
      });

    starSim.stop();

    const starSignalParticles = [];
    const nStarPart = Math.min(starEdges.length, SUBVIEW_SIGNAL_MAX);
    for (let pi = 0; pi < nStarPart; pi++) {
      const ed = starEdges[pi];
      starSignalParticles.push({
        edge: ed,
        progress: Math.random(),
        speed: 0.003 + Math.random() * 0.004,
        color: ed.color || 0x4ade80,
      });
    }

    starContainer._sim = starSim;
    starContainer._edges = starEdges;
    starContainer._edgeGfx = starEdgeGfx;
    starContainer._growthGfx = starGrowthGfx;
    starContainer._signalGfx = starSignalGfx;
    starContainer._signalParticles = starSignalParticles;
    starContainer._nodes = starNodes;
    starContainer._growthTree = growthTree;
    starContainer._growthIdToNode = growthIdToNode;
    starContainer._growthAnimSet = growthIdAnimSet;
    starContainer._growthDepthMap = depthMap;
    starContainer._growthAnimNodes = animNodes.slice();
    starContainer._growthPhaseComplete = false;

    const titleText = new PIXI.Text((dirId && dirId.split('/').pop()) || dirId || '', {
      fontFamily: 'Syne, sans-serif',
      fontSize: 16,
      fill: 0x6366f1,
      align: 'center',
    });
    titleText.alpha = 0.25;
    titleText.anchor.set(0.5);
    titleText.position.set(centerX, centerY);
    titleText.eventMode = 'none';
    starContainer.addChild(titleText);
    starViewTitle = titleText;

    const growthMaster = gsap.timeline({
      onKill: () => {
        starContainer._growthTl = null;
      },
    });
    starContainer._growthTl = growthMaster;

    if (growthTree && bfsOrder.length) {
      const rootSn = growthTree.root;
      rootSn.x = centerX;
      rootSn.y = centerY;
      rootSn.container.position.set(centerX, centerY);
      rootSn._growEdgeU = 1;
      const rootScale = { s: 0 };
      growthMaster.to(
        rootScale,
        {
          s: 1,
          duration: 0.3,
          ease: 'back.out(1.4)',
          onUpdate: () => {
            const sc = Math.max(0.001, rootScale.s);
            rootSn.container.scale.set(sc, sc);
          },
        },
        0
      );
      growthMaster.to(
        rootSn.container,
        { alpha: 1, duration: 0.12, ease: 'power2.out' },
        0
      );

      const maxDepth = bfsOrder.reduce(
        (m, n) => Math.max(m, growthTree.depth[n.growthId] || 0),
        0
      );
      const rootIntroSec = 0.32;
      let tLayer = rootIntroSec;
      if (maxDepth >= 1) {
        const budget = STAR_GROWTH_TOTAL_SEC - rootIntroSec;
        let layerGap =
          maxDepth > 1 ? Math.min(0.02, (budget * 0.2) / (maxDepth - 1)) : 0;
        let layerDur = (budget - layerGap * (maxDepth - 1)) / maxDepth;
        if (layerDur < 0.015) {
          layerGap = 0;
          layerDur = budget / maxDepth;
        }
        for (let d = 1; d <= maxDepth; d++) {
          const layerNodes = bfsOrder.filter(
            n => (growthTree.depth[n.growthId] || 0) === d
          );
          for (let li = 0; li < layerNodes.length; li++) {
            const node = layerNodes[li];
            const pos = growthPositions[node.growthId];
            if (!pos) continue;
            const parentId = growthTree.parent[node.growthId];
            const parentSn = parentId != null ? growthIdToNode.get(parentId) : rootSn;
            if (!parentSn) continue;
            node._growEdgeU = 0;
            const prog = { u: 0 };
            growthMaster.to(
              prog,
              {
                u: 1,
                duration: layerDur,
                ease: 'back.out(1.4)',
                delay: tLayer,
                onStart: () => {
                  node._gx0 = parentSn.x;
                  node._gy0 = parentSn.y;
                  node.x = node._gx0;
                  node.y = node._gy0;
                  node.container.position.set(node._gx0, node._gy0);
                  node.container.alpha = 1;
                  node.container.scale.set(0.02, 0.02);
                },
                onUpdate: () => {
                  const t = prog.u;
                  const ox = node._gx0;
                  const oy = node._gy0;
                  node.x = ox + (pos.x - ox) * t;
                  node.y = oy + (pos.y - oy) * t;
                  node.container.position.set(node.x, node.y);
                  node._growEdgeU = t;
                  const sc = 0.02 + 0.98 * t;
                  node.container.scale.set(sc, sc);
                },
              },
              0
            );
          }
          tLayer += layerDur + (d < maxDepth ? layerGap : 0);
        }
      }
    } else {
      for (let fi = 0; fi < starNodes.length; fi++) {
        const sn = starNodes[fi];
        sn.x = centerX + (rand() - 0.5) * 24;
        sn.y = centerY + (rand() - 0.5) * 24;
        sn.container.position.set(sn.x, sn.y);
        const st = Math.min(fi * 0.03, STAR_GROWTH_TOTAL_SEC * 0.45);
        growthMaster.to(
          sn.container,
          { alpha: 1, duration: 0.32, ease: 'back.out(1.4)' },
          st
        );
        growthMaster.to(
          sn.container.scale,
          { x: 1, y: 1, duration: 0.32, ease: 'back.out(1.4)' },
          st
        );
      }
    }

    for (let ri = 0; ri < starNodes.length; ri++) {
      const sn = starNodes[ri];
      if (!growthIdAnimSet.has(sn.growthId)) {
        sn.x = centerX;
        sn.y = centerY;
        sn.container.position.set(centerX, centerY);
        sn.container.alpha = 0;
        sn.container.scale.set(1, 1);
        sn._growEdgeU = 0;
      }
    }

    const migrateProxy = { _p: 0 };
    growthMaster.to(
      migrateProxy,
      {
        _p: 1,
        duration: STAR_MIGRATE_SEC,
        ease: 'power2.inOut',
        onStart: () => {
          for (const sn of starNodes) {
            sn._gxEnd = sn.x;
            sn._gyEnd = sn.y;
            sn.vx = 0;
            sn.vy = 0;
          }
          starSim.alpha(1);
          for (let tk = 0; tk < 400; tk++) {
            starSim.tick();
          }
          for (const sn of starNodes) {
            sn._fx = sn.x;
            sn._fy = sn.y;
            sn.vx = 0;
            sn.vy = 0;
          }
          for (const sn of starNodes) {
            sn.x = sn._gxEnd;
            sn.y = sn._gyEnd;
            sn.container.position.set(sn.x, sn.y);
          }
        },
        onUpdate: () => {
          const t = migrateProxy._p;
          for (const sn of starNodes) {
            sn.x = sn._gxEnd + (sn._fx - sn._gxEnd) * t;
            sn.y = sn._gyEnd + (sn._fy - sn._gyEnd) * t;
            sn.container.position.set(sn.x, sn.y);
            if (!growthIdAnimSet.has(sn.growthId)) {
              sn.container.alpha = t;
            }
          }
        },
        onComplete: () => {
          for (const sn of starNodes) {
            sn.x = sn._fx;
            sn.y = sn._fy;
            sn.container.position.set(sn.x, sn.y);
            sn._growEdgeU = 1;
          }
          starContainer._growthPhaseComplete = true;
          starSim.alpha(1).restart();
          gsap.to(starEdgeGfx, { alpha: 1, duration: 0.2, ease: 'power2.out' });
          gsap.to(starSignalGfx, { alpha: 1, duration: 0.2, ease: 'power2.out' });
        },
      },
      STAR_GROWTH_TOTAL_SEC
    );

    growthMaster.eventCallback('onComplete', () => {
      starContainer._growthTl = null;
    });
  }

  function createPlanetView(fileData, symbols) {
    cleanupPlanetView();
    if (!world || !app) return;
    const planetContainer = new PIXI.Container();
    planetContainer.eventMode = 'passive';
    planetContainer._omnixType = 'planet';
    planetContainer.alpha = 1;
    world.addChild(planetContainer);

    const centerX = app.screen.width / 2;
    const centerY = app.screen.height / 2;
    planetContainer._planetCenterX = centerX;
    planetContainer._planetCenterY = centerY;
    const maxSymbols = Math.min(symbols.length, 100);
    const fp = fileData.filePath || resolveDirFilePath(selectedDir, fileData.name);
    const boundaryR =
      Math.min(app.screen.width, app.screen.height) * 0.36;
    planetContainer._planetBoundaryR = boundaryR;

    const planetEdgeGfx = new PIXI.Graphics();
    planetEdgeGfx.eventMode = 'none';
    planetContainer.addChild(planetEdgeGfx);

    const planetSignalGfx = new PIXI.Graphics();
    planetSignalGfx.eventMode = 'none';
    planetSignalGfx.alpha = 1;
    planetContainer.addChild(planetSignalGfx);

    planetNodes = [];
    const symSlice = symbols.slice(0, maxSymbols);

    for (let j = 0; j < maxSymbols; j++) {
      const sym = symSlice[j];
      const val = sym.complexity != null && sym.complexity > 0 ? sym.complexity : 1;
      const radius = Math.sqrt(val) * 4 + 8;
      const classification = classifyPlanetSymbol(sym);
      const color = classification.color;

      const jx = centerX + (Math.random() - 0.5) * 140;
      const jy = centerY + (Math.random() - 0.5) * 140;

      const symContainer = new PIXI.Container();
      symContainer.position.set(jx, jy);
      symContainer.alpha = 0;
      symContainer.eventMode = 'static';
      symContainer.cursor = 'pointer';

      const glow = new PIXI.Graphics();
      glow.beginFill(color, 0.12);
      glow.drawCircle(0, 0, radius * 2.5);
      glow.endFill();
      glow.alpha = 0.55;
      symContainer.addChild(glow);

      const cellFill = new PIXI.Graphics();
      cellFill.beginFill(color, 0.25);
      cellFill.drawCircle(0, 0, radius);
      cellFill.endFill();
      symContainer.addChild(cellFill);

      const membraneGfx = new PIXI.Graphics();
      symContainer.addChild(membraneGfx);

      const nucleus = new PIXI.Graphics();
      nucleus.beginFill(color, 0.9);
      nucleus.drawCircle(0, 0, 3);
      nucleus.endFill();
      symContainer.addChild(nucleus);

      const rawName = sym.name || '';
      const nm =
        rawName.length > 20 ? rawName.slice(0, 18) + '…' : rawName;
      const label = new PIXI.Text(nm, {
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        fill: 0xe2e8f0,
        align: 'center',
      });
      label.alpha = 0.8;
      label.anchor.set(0.5, 0);
      label.position.set(0, radius + 5);
      label.eventMode = 'none';
      label.visible = radius > 12;
      symContainer.addChild(label);

      const symHitR = Math.max(radius * 2.8, radius + 36);
      symContainer.hitArea = new PIXI.Circle(0, 0, symHitR);

      planetContainer.addChild(symContainer);

      gsap.to(symContainer, {
        alpha: 1,
        duration: 0.35,
        delay: j * 0.015,
        ease: 'power2.out',
      });

      const pnRef = {
        container: symContainer,
        symbol: sym,
        x: jx,
        y: jy,
        vx: 0,
        vy: 0,
        radius,
        color,
        classification,
        glow,
        cellFill,
        membraneGfx,
        nucleus,
        label,
        index: j,
        _hover: false,
      };

      symContainer.on('pointerdown', e => {
        const btn = pointerEventButton(e);
        if (btn === 2) {
          e.stopPropagation();
          const oe = e.data && e.data.originalEvent;
          if (oe && oe.preventDefault) oe.preventDefault();
          void openXrayForPlanetFunction(fileData, sym, classification, fp);
          return;
        }
        if (btn !== 0) return;
        e.stopPropagation();
        if (
          (sym.type === 'function' || sym.type === 'class' || sym.type === 'method') &&
          typeof studio._options.onFunctionNodeClick === 'function' &&
          sym &&
          sym.id
        ) {
          try {
            studio._options.onFunctionNodeClick(String(sym.id));
          } catch (_e) { /* */ }
          return;
        }
        showSymbolDetailPopup(sym, fileData);
      });
      symContainer.on('pointerover', () => {
        pnRef._hover = true;
        gsap.to(symContainer.scale, { x: 1.2, y: 1.2, duration: 0.2 });
      });
      symContainer.on('pointerout', () => {
        pnRef._hover = false;
        gsap.to(symContainer.scale, { x: 1, y: 1, duration: 0.2 });
      });

      planetNodes.push(pnRef);
    }

    const planetEdges = buildPlanetEdgeList(fp, symSlice, planetNodes);

    const planetSim = d3
      .forceSimulation(planetNodes)
      .force('center', d3.forceCenter(centerX, centerY))
      .force('charge', d3.forceManyBody().strength(-60))
      .force('collision', d3.forceCollide().radius(d => d.radius * 2 + 8))
      .force('link', d3.forceLink(planetEdges).distance(90).strength(0.4))
      .force('x', d3.forceX(centerX).strength(0.06))
      .force('y', d3.forceY(centerY).strength(0.06))
      .alphaDecay(0.02)
      .on('tick', () => {
        for (const pn of planetNodes) {
          pn.container.position.set(pn.x, pn.y);
        }
      });

    const planetSignalParticles = [];
    const nPlanetPart = Math.min(planetEdges.length, SUBVIEW_SIGNAL_MAX);
    for (let qi = 0; qi < nPlanetPart; qi++) {
      const ed = planetEdges[qi];
      planetSignalParticles.push({
        edge: ed,
        progress: Math.random(),
        speed: 0.003 + Math.random() * 0.004,
        color: ed.color || 0x4ade80,
      });
    }

    planetContainer._sim = planetSim;
    planetContainer._edges = planetEdges;
    planetContainer._edgeGfx = planetEdgeGfx;
    planetContainer._signalGfx = planetSignalGfx;
    planetContainer._signalParticles = planetSignalParticles;
    planetContainer._nodes = planetNodes;

    const titleText = new PIXI.Text(fileData.name || '', {
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 14,
      fill: 0x06b6d4,
      align: 'center',
    });
    titleText.alpha = 0.35;
    titleText.anchor.set(0.5);
    titleText.position.set(centerX, centerY);
    titleText.eventMode = 'none';
    planetContainer.addChild(titleText);
    planetViewTitle = titleText;
    studio?.setViewContext?.('planet-ready');
  }

  function transitionToStar(dirId, clickedSimNode) {
    if (!model || !world || !app) return;
    if (viewLevel !== 'galaxy') return;
    hideSymbolPopup();
    killTweens();
    selectedDir = dirId;
    updateBreadcrumb();

    let starClicked = clickedSimNode;
    if (!starClicked) {
      starClicked = simNodes.find(sn => sn.kind === 'directory' && sn.dirId === dirId) || null;
    }
    if (!starClicked) {
      gsap.set(layerEdges, { alpha: 0 });
      nodePool.forEach(p => {
        if (p.container) gsap.set(p.container, { alpha: 0.08 });
      });
      const filesEarly = model.dirFilesMap[dirId] || [];
      gsap.delayedCall(STAR_DRILL_CREATE_DELAY_SEC, () => {
        createStarView(dirId, filesEarly);
      });
      return;
    }

    const centerLocal = world.toLocal(new PIXI.Point(app.screen.width / 2, app.screen.height / 2));

    for (let i = 0; i < simNodes.length; i++) {
      const simNode = simNodes[i];
      const pool = nodePool[i];
      if (!pool || !pool.container) continue;
      const isClicked = simNode === starClicked;
      gsap.killTweensOf(pool.container);
      gsap.killTweensOf(pool.container.scale);
      if (isClicked) {
        const sx = pool.container.scale.x || 1;
        const sy = pool.container.scale.y || 1;
        gsap.fromTo(
          pool.container.scale,
          { x: sx, y: sy },
          {
            x: sx * 1.1,
            y: sy * 1.1,
            duration: 0.1,
            ease: 'power2.out',
            yoyo: true,
            repeat: 1,
          }
        );
        gsap.to(pool.container, {
          x: centerLocal.x,
          y: centerLocal.y,
          duration: 0.5,
          ease: 'power2.inOut',
          onComplete: () => {
            gsap.to(pool.container, { alpha: 0, duration: 0.3, ease: 'power2.out' });
          },
        });
      } else {
        gsap.to(pool.container, { alpha: 0.1, duration: 0.4, ease: 'power2.out' });
      }
    }

    gsap.to(layerEdges, { alpha: 0, duration: 0.3 });

    const files = model.dirFilesMap[dirId] || [];
    gsap.delayedCall(STAR_DRILL_CREATE_DELAY_SEC, () => {
      if (viewLevel !== 'galaxy' || selectedDir !== dirId) return;
      createStarView(dirId, files);
    });
  }

  function transitionToPlanet(fileData) {
    if (!model || !world || !app || viewLevel !== 'star') return;
    console.debug('[slice17c1] calling transitionToPlanet', {
      galaxy: fileData && fileData.name != null ? String(fileData.name) : '',
    });
    hideSymbolPopup();
    killTweens();
    if (planetCreateDelayed) {
      planetCreateDelayed.kill();
      planetCreateDelayed = null;
    }
    for (let ci = 0; ci < world.children.length; ci++) {
      const ch = world.children[ci];
      if (ch._omnixType === 'star') {
        if (ch._growthTl) {
          ch._growthTl.kill();
          ch._growthTl = null;
        }
        ch._growthPhaseComplete = true;
        if (ch._sim) ch._sim.stop();
        if (ch._edgeGfx) ch._edgeGfx.clear();
        if (ch._growthGfx) ch._growthGfx.clear();
        if (ch._signalGfx) ch._signalGfx.clear();
      }
    }
    for (let si = 0; si < starNodes.length; si++) {
      const sn = starNodes[si];
      if (sn && sn.container) {
        sn.x = sn.container.x;
        sn.y = sn.container.y;
      }
    }
    const symbols = getSymbolsForFile(fileData.filePath || fileData.name, selectedDir);
    selectedFile = fileData;
    viewLevel = 'planet';
    notifyViewerScope({
      kind: 'file',
      path: normalizeFsPath(fileData.filePath || fileData.name || ''),
    });
    notifyScopeVisualEmpty(null);
    updateBreadcrumb();

    const cx = app.screen.width / 2;
    const cy = app.screen.height / 2;

    for (let i = 0; i < starNodes.length; i++) {
      const sn = starNodes[i];
      if (!sn || !sn.container) continue;
      const isSel = sn.fileData === fileData;
      gsap.killTweensOf(sn.container);
      gsap.killTweensOf(sn.container.scale);
      if (isSel) {
        sn.container.alpha = 1;
        const tl = gsap.timeline();
        tl.to(
          sn.container.scale,
          { x: 1.1, y: 1.1, duration: 0.2, ease: 'power2.out' },
          0
        );
        tl.to(
          sn.container,
          { x: cx, y: cy, duration: 0.35, ease: 'power2.inOut' },
          0.15
        );
        tl.to(
          sn.container.scale,
          { x: 1.75, y: 0.9, duration: 0.28, ease: 'power1.inOut' },
          0.28
        );
        tl.to(
          sn.container.scale,
          { x: 1.2, y: 1.15, duration: 0.22, ease: 'sine.inOut' },
          0.52
        );
        tl.to(sn.container.scale, { x: 0.85, y: 1.08, duration: 0.18, ease: 'sine.inOut' }, 0.72);
        tl.to(sn.container, { alpha: 0, duration: 0.25, ease: 'power2.in' }, 0.75);
      } else {
        gsap.to(sn.container, { alpha: 0.2, duration: 0.22, ease: 'power2.out' });
      }
    }

    planetCreateDelayed = gsap.delayedCall(1, () => {
      planetCreateDelayed = null;
      if (viewLevel !== 'planet' || !selectedFile || selectedFile !== fileData) return;
      createPlanetView(fileData, symbols);
    });
    console.debug('[slice17c1] transitionToPlanet returned', { success: true });
  }

  function runPlanetReverseMitosis(onDone) {
    if (!world || !app) {
      onDone();
      return;
    }
    const pc = world.children.find(c => c._omnixType === 'planet');
    if (!pc) {
      onDone();
      return;
    }
    if (!planetNodes.length) {
      cleanupPlanetView();
      onDone();
      return;
    }
    planetReverseActive = true;
    if (pc._sim) pc._sim.stop();

    const cx = app.screen.width / 2;
    const cy = app.screen.height / 2;
    const nodes = planetNodes.slice();

    if (pc._signalGfx) gsap.killTweensOf(pc._signalGfx);
    if (planetViewTitle) gsap.killTweensOf(planetViewTitle);

    const tl = gsap.timeline({
      onComplete: () => {
        cleanupPlanetView();
        planetReverseActive = false;
        onDone();
      },
    });

    if (pc._signalGfx) tl.to(pc._signalGfx, { alpha: 0, duration: 0.2, ease: 'power2.out' }, 0);
    if (planetViewTitle) tl.to(planetViewTitle, { alpha: 0, duration: 0.2, ease: 'power2.out' }, 0);

    for (let i = 0; i < nodes.length; i++) {
      const pn = nodes[i];
      if (!pn || !pn.container) continue;
      gsap.killTweensOf(pn.container);
      gsap.killTweensOf(pn.container.scale);
      tl.to(
        pn.container,
        { x: cx, y: cy, duration: 0.55, ease: 'power2.in' },
        0.18
      );
      tl.to(
        pn.container.scale,
        { x: 0.04, y: 0.04, duration: 0.52, ease: 'power2.in' },
        0.22
      );
    }

    tl.to(pc, { alpha: 0, duration: 0.2, ease: 'power2.in' }, 0.82);
    tl.set({}, {}, 1);
  }

  function runStarReverseCollapse() {
    hideSymbolPopup();
    if (!world || !app) {
      cleanupStarView();
      viewLevel = 'galaxy';
      selectedDir = null;
      selectedFile = null;
      restoreGalaxyView();
      notifyScopeVisualEmpty(null);
      notifyViewerScope({ kind: 'repo' });
      return;
    }
    const sc = world.children.find(c => c._omnixType === 'star');
    if (!sc || !starNodes.length) {
      cleanupStarView();
      viewLevel = 'galaxy';
      selectedDir = null;
      selectedFile = null;
      restoreGalaxyView();
      notifyScopeVisualEmpty(null);
      notifyViewerScope({ kind: 'repo' });
      return;
    }
    starReverseActive = true;
    closeXray();
    if (sc._growthTl) {
      sc._growthTl.kill();
      sc._growthTl = null;
    }
    if (sc._sim) sc._sim.stop();
    const cx = app.screen.width / 2;
    const cy = app.screen.height / 2;
    const depthMap = sc._growthDepthMap || new Map();
    const animNodes =
      sc._growthAnimNodes && sc._growthAnimNodes.length
        ? sc._growthAnimNodes.slice()
        : starNodes.slice();
    animNodes.sort((a, b) => (depthMap.get(b.growthId) || 0) - (depthMap.get(a.growthId) || 0));

    if (starViewTitle) gsap.killTweensOf(starViewTitle);

    sc._growthPhaseComplete = true;

    const seen = new Set();
    const tl = gsap.timeline({
      onComplete: () => {
        starReverseActive = false;
        cleanupStarView();
        viewLevel = 'galaxy';
        selectedDir = null;
        selectedFile = null;
        restoreGalaxyView();
        notifyScopeVisualEmpty(null);
        notifyViewerScope({ kind: 'repo' });
      },
    });

    if (sc._signalGfx) tl.to(sc._signalGfx, { alpha: 0, duration: 0.15, ease: 'power2.out' }, 0);
    if (sc._edgeGfx) tl.to(sc._edgeGfx, { alpha: 0, duration: 0.15, ease: 'power2.out' }, 0);
    if (sc._growthGfx) tl.to(sc._growthGfx, { alpha: 0, duration: 0.12, ease: 'power2.out' }, 0);
    if (starViewTitle) tl.to(starViewTitle, { alpha: 0, duration: 0.12 }, 0);

    for (let i = 0; i < animNodes.length; i++) {
      const sn = animNodes[i];
      if (!sn || !sn.container || seen.has(sn)) continue;
      seen.add(sn);
      gsap.killTweensOf(sn.container);
      gsap.killTweensOf(sn.container.scale);
      const o = { x: sn.x, y: sn.y };
      tl.to(
        o,
        {
          x: cx,
          y: cy,
          duration: 0.5,
          ease: 'power2.in',
          onUpdate: () => {
            sn.x = o.x;
            sn.y = o.y;
            sn.container.position.set(o.x, o.y);
          },
        },
        0.06 + i * 0.026
      );
      tl.to(
        sn.container.scale,
        { x: 0.05, y: 0.05, duration: 0.46, ease: 'power2.in' },
        0.08 + i * 0.026
      );
      tl.to(sn.container, { alpha: 0, duration: 0.18, ease: 'power2.in' }, 0.58 + i * 0.022);
    }

    for (let ri = 0; ri < starNodes.length; ri++) {
      const sn = starNodes[ri];
      if (seen.has(sn)) continue;
      if (!sn || !sn.container) continue;
      gsap.killTweensOf(sn.container);
      tl.to(
        sn.container,
        { x: cx, y: cy, alpha: 0, duration: 0.38, ease: 'power2.in' },
        0.04 + ri * 0.018
      );
    }

    tl.to(sc, { alpha: 0, duration: 0.2, ease: 'power2.in' }, 0.88);
  }

  function goBack() {
    hideSymbolPopup();
    if (viewLevel === 'planet') {
      if (planetReverseActive) return;
      if (planetCreateDelayed) {
        planetCreateDelayed.kill();
        planetCreateDelayed = null;
        viewLevel = 'star';
        selectedFile = null;
        for (let i = 0; i < starNodes.length; i++) {
          const sn = starNodes[i];
          if (!sn || !sn.container) continue;
          gsap.killTweensOf(sn.container);
          gsap.killTweensOf(sn.container.scale);
          sn.container.scale.set(1, 1);
          gsap.to(sn.container, { alpha: 1, duration: 0.25, ease: 'power2.out' });
        }
        const sc = world && world.children.find(c => c._omnixType === 'star');
        if (sc && sc._sim) sc._sim.alpha(0.45).restart();
        updateBreadcrumb();
        if (selectedDir) {
          notifyViewerScope({ kind: 'directory', path: normalizeFsPath(selectedDir) });
        }
        return;
      }
      closeXray();
      runPlanetReverseMitosis(() => {
        viewLevel = 'star';
        selectedFile = null;
        restoreStarView();
        if (selectedDir) {
          notifyViewerScope({ kind: 'directory', path: normalizeFsPath(selectedDir) });
        }
      });
    } else if (viewLevel === 'star') {
      if (starReverseActive) return;
      runStarReverseCollapse();
    }
  }

  function stopSimulation() {
    if (simulation) {
      simulation.stop();
      simulation = null;
    }
  }

  function startSimulation(nodes, links) {
    stopSimulation();
    labelTop20Key = '';
    labelTop20Set = null;
    nodePool.forEach(p => {
      if (p && p.container) p.container.scale.set(1);
    });
    simNodes = nodes.map(n => Object.assign({}, n));
    simLinks = links.map(l => ({
      source: l.source,
      target: l.target,
      type: l.type,
      weight: l.weight,
    }));
    simLinks.forEach(l => {
      if (l._curveOffset == null) {
        l._curveOffset = (Math.random() - 0.5) * 30;
        l._curveOffset2 = (Math.random() - 0.5) * 15;
      }
    });

    const d3f = typeof d3 !== 'undefined' ? d3 : window.d3;
    if (!d3f || !d3f.forceSimulation) {
      console.error('d3-force not available');
      for (let _zi = 0; _zi < MYCELIUM_POOL_SIZE; _zi++) myceliumParticlePool[_zi].active = false;
      return;
    }

    if (!simNodes.length) {
      for (let _zi = 0; _zi < MYCELIUM_POOL_SIZE; _zi++) myceliumParticlePool[_zi].active = false;
      if (viewLevel === 'galaxy') {
        notifyScopeVisualEmpty({ scopePath: '', viewLevel: 'galaxy' });
      }
      syncPixiFromSim();
      return;
    }

    const isGalaxyView = simNodes.length > 0 && simNodes[0].kind === 'directory';
    if (isGalaxyView) {
      notifyScopeVisualEmpty(null);
    }
    const chargeStrength = isGalaxyView ? -150 : -420;
    const collidePad = isGalaxyView ? 6 : 16;
    simulation = d3f.forceSimulation(simNodes)
      .force('charge', d3f.forceManyBody().strength(chargeStrength))
      .force('center', d3f.forceCenter(0, 0))
      .force(
        'collide',
        d3f.forceCollide().radius(d => {
          if (isGalaxyView) {
            const mass = d.childCount || 10;
            return 8 + Math.sqrt(mass) * 1.5;
          }
          return (d.radius || 14) + collidePad;
        })
      )
      .alphaDecay(0.022)
      .velocityDecay(0.6);
    if (simLinks.length) {
      const linkDistance = isGalaxyView
        ? l => {
            const w = l.weight || 1;
            return 40 + 120 / Math.sqrt(w + 1);
          }
        : l => {
            const w = l.weight || 1;
            return 100 + 220 / Math.sqrt(w + 1);
          };
      const linkStrength = isGalaxyView ? 0.5 : 0.32;
      simulation.force(
        'link',
        d3f.forceLink(simLinks).id(d => d.id).distance(linkDistance).strength(linkStrength)
      );
    }

    simulation.alpha(1);
    for (let i = 0; i < 120; i++) simulation.tick();

    for (let hi = 0; hi < simNodes.length; hi++) {
      const sn = simNodes[hi];
      sn._heartbeatPhase = Math.random() * Math.PI * 2;
      sn._heartbeatSpeed = 0.8 + Math.random() * 0.4;
    }
    if (isGalaxyView) rebuildMyceliumFlowPool();
    else for (let _zi = 0; _zi < MYCELIUM_POOL_SIZE; _zi++) myceliumParticlePool[_zi].active = false;

    syncPixiFromSim();
  }

  function top20LabelIds() {
    if (simNodes.length <= 20) return null;
    const key = viewLevel + '\0' + simNodes.map(n => n.id).join('|');
    if (key === labelTop20Key && labelTop20Set) return labelTop20Set;
    labelTop20Key = key;
    if (viewLevel === 'star') {
      labelTop20Set = new Set(
        [...simNodes]
          .sort((a, b) => (b.radius || 0) - (a.radius || 0))
          .slice(0, 20)
          .map(n => n.id)
      );
    } else if (viewLevel === 'planet') {
      labelTop20Set = new Set(
        [...simNodes]
          .sort((a, b) => {
            const va = (a.raw && a.raw.val) || 0;
            const vb = (b.raw && b.raw.val) || 0;
            if (vb !== va) return vb - va;
            return (b.radius || 0) - (a.radius || 0);
          })
          .slice(0, 20)
          .map(n => n.id)
      );
    } else {
      labelTop20Set = null;
    }
    return labelTop20Set;
  }

  function graphIdToFilePath(gid) {
    if (!gid || typeof gid !== 'string') return '';
    if (gid.startsWith('dark:')) return '';
    const ix = gid.indexOf('::');
    return ix >= 0 ? gid.slice(0, ix) : gid;
  }

  function findSimDirForGraphNode(gid) {
    const fp = graphIdToFilePath(gid);
    if (!fp) return null;
    const d = dirname(fp);
    if (d === undefined || d === null || d === '') return null;
    return simNodes.find(sn => sn.kind === 'directory' && sn.dirId === d) || null;
  }

  /** Longest-prefix galaxy directory node for a directory path (top dirs only). */
  function findGalaxyDirSimNodeForDirPath(dirPath) {
    if (dirPath === undefined || dirPath === null || viewLevel !== 'galaxy' || !simNodes.length) {
      return null;
    }
    const pathStr = String(dirPath);
    let best = null;
    let bestLen = -1;
    for (let i = 0; i < simNodes.length; i++) {
      const sn = simNodes[i];
      if (sn.kind !== 'directory') continue;
      const id = sn.dirId || (sn.raw && sn.raw.id) || '';
      if (pathStr === id || (id && pathStr.startsWith(id + '/'))) {
        if (id.length > bestLen) {
          bestLen = id.length;
          best = sn;
        }
      }
    }
    return best;
  }

  function findGalaxyDirSimNodeForFilePath(filePath) {
    if (!filePath) return null;
    const d = dirname(String(filePath));
    return findGalaxyDirSimNodeForDirPath(d);
  }

  function xrayEndpoint(gid, nodeById) {
    const id = typeof gid === 'object' && gid && gid.id ? gid.id : gid;
    if (!id || typeof id !== 'string') return { dir: null, label: '?', file: '' };
    const n = nodeById.get(id);
    const fp = graphIdToFilePath(id);
    if (fp) {
      return {
        dir: dirname(fp),
        label: basename(fp).split('::')[0] || fp,
        file: fp,
      };
    }
    if (n && n.type === 'dark_matter') {
      return {
        dir: null,
        label: n.name || id.replace(/^dark:/, '') || 'dark',
        file: '',
        isDark: true,
      };
    }
    return { dir: null, label: String(id).split('::')[0].split('/').pop() || id, file: '' };
  }

  function buildHealthBar(label, percent, color) {
    const p = Math.max(0, Math.min(100, percent));
    return (
      '<div style="margin-bottom: 8px;">' +
      '<div style="display: flex; justify-content: space-between; margin-bottom: 3px;">' +
      '<span style="font-size: 11px; color: #94a3b8;">' + escapeHtml(label) + '</span>' +
      '<span style="font-size: 11px; color: ' + color + ';">' + p + '%</span>' +
      '</div>' +
      '<div style="height: 4px; background: rgba(99,102,241,0.1); border-radius: 2px; overflow: hidden;">' +
      '<div style="height: 100%; width: ' + p + '%; background: ' + color + '; border-radius: 2px;"></div>' +
      '</div></div>'
    );
  }

  function detectIssues(dirId, files, incoming, outgoing, entangledCount, darkForceCount, rawLinks) {
    const issues = [];

    const totalFunctions = files.reduce((sum, f) => sum + (f.symbolCount || 0), 0);

    const circularImports = rawLinks.filter(
      l =>
        l.type === 'ENTANGLED' &&
        l.metadata &&
        (typeof l.metadata === 'string' ? l.metadata.includes('circular') : false) &&
        ((typeof l.source === 'string' && l.source.startsWith(dirId)) ||
          (typeof l.target === 'string' && l.target.startsWith(dirId)))
    );
    if (circularImports.length > 0) {
      const names = circularImports.slice(0, 3).map(l => {
        const other =
          typeof l.source === 'string' && l.source.startsWith(dirId) ? l.target : l.source;
        return typeof other === 'string' ? other.split('/').pop().split('::')[0] : '?';
      });
      issues.push({
        severity: 'high',
        icon: '🔴',
        title: `Circular import${circularImports.length > 1 ? 's' : ''} detected`,
        detail: `${names.join(', ')} — mutual dependency creates fragile coupling`,
        fix: 'Extract shared types into a separate module',
      });
    }

    if (entangledCount > 8) {
      issues.push({
        severity: 'high',
        icon: '🔴',
        title: `${entangledCount} entangled pairs — extreme coupling`,
        detail: 'Changing this module risks breaking many dependents',
        fix: 'Introduce API contracts/interfaces to decouple',
      });
    } else if (entangledCount > 4) {
      issues.push({
        severity: 'med',
        icon: '🟡',
        title: `${entangledCount} entangled pairs — moderate coupling`,
        detail: 'Some tight coupling detected across module boundaries',
        fix: 'Consider dependency inversion for the most entangled pairs',
      });
    }

    if (darkForceCount > 3) {
      issues.push({
        severity: 'med',
        icon: '🟡',
        title: `${darkForceCount} dark matter dependencies`,
        detail: 'Hidden env/config dependencies — missing var = silent failure',
        fix: 'Add validation: check all required env vars at startup',
      });
    }

    const godFiles = files.filter(f => (f.symbolCount || 0) > 100);
    if (godFiles.length > 0) {
      issues.push({
        severity: 'high',
        icon: '🔴',
        title: `God file: ${godFiles[0].name} (${godFiles[0].symbolCount} symbols)`,
        detail: 'Too many responsibilities in one file — hard to test and maintain',
        fix: 'Split into focused modules by responsibility',
      });
    }

    if (totalFunctions > 300) {
      issues.push({
        severity: 'med',
        icon: '🟡',
        title: `High complexity: ${totalFunctions} functions`,
        detail: 'This module is very large — consider splitting',
        fix: 'Extract sub-modules by domain/feature',
      });
    }

    if (incoming > 20) {
      issues.push({
        severity: 'med',
        icon: '🟡',
        title: `High fan-in: ${incoming} incoming dependencies`,
        detail: 'Many modules depend on this — changes have wide blast radius',
        fix: 'Use versioned interfaces to prevent breaking changes',
      });
    }

    if (outgoing > 15) {
      issues.push({
        severity: 'med',
        icon: '🟡',
        title: `High fan-out: ${outgoing} outgoing calls`,
        detail: 'This module depends on many others — fragile to external changes',
        fix: 'Introduce a facade or mediator pattern',
      });
    }

    if (incoming === 0 && outgoing === 0 && files.length > 0) {
      issues.push({
        severity: 'low',
        icon: '🟢',
        title: 'Orphan module — no external connections',
        detail: 'This module is isolated — possibly dead code or missing imports',
        fix: 'Verify this module is actually used; remove if dead code',
      });
    }

    const order = { high: 0, med: 1, low: 2 };
    issues.sort((a, b) => order[a.severity] - order[b.severity]);

    return issues;
  }

  function buildXrayHTML(simNode) {
    const raw = rawGraphData || (model && model.raw);
    const nodeById = model && model.nodeById;
    if (!raw || !nodeById || !model) return '<p style="color:#64748b;font-size:12px;">No graph data.</p>';

    const dirId = simNode.dirId != null ? simNode.dirId : (simNode.raw && simNode.raw.id) || '';
    const dirName = dirId ? basename(dirId) || dirId : '(root)';
    const rawLinks = raw.links || [];
    const filesBase = (model.dirFilesMap[dirId] || []).map(f => ({ ...f }));

    const connCountByFile = new Map();
    for (const link of rawLinks) {
      const sid = typeof link.source === 'object' ? link.source.id : link.source;
      const tid = typeof link.target === 'object' ? link.target.id : link.target;
      const sf = graphIdToFilePath(sid);
      const tf = graphIdToFilePath(tid);
      if (sf) {
        const d = dirname(sf);
        if (d === dirId) {
          const k = basename(sf);
          connCountByFile.set(k, (connCountByFile.get(k) || 0) + 1);
        }
      }
      if (tf) {
        const d = dirname(tf);
        if (d === dirId) {
          const k = basename(tf);
          connCountByFile.set(k, (connCountByFile.get(k) || 0) + 1);
        }
      }
    }
    filesBase.sort((a, b) => {
      const ca = connCountByFile.get(a.name) || 0;
      const cb = connCountByFile.get(b.name) || 0;
      if (cb !== ca) return cb - ca;
      return (b.symbolCount || 0) - (a.symbolCount || 0);
    });

    const totalFunctions = filesBase.reduce((sum, f) => sum + (f.symbolCount || 0), 0);

    let incoming = 0;
    let outgoing = 0;
    const connections = [];

    for (const link of rawLinks) {
      const sid = typeof link.source === 'object' ? link.source.id : link.source;
      const tid = typeof link.target === 'object' ? link.target.id : link.target;
      const sa = xrayEndpoint(sid, nodeById);
      const tb = xrayEndpoint(tid, nodeById);
      const sIn = sa.dir === dirId;
      const tIn = tb.dir === dirId;
      if (sIn && tIn) continue;
      if (!sIn && !tIn) continue;

      const lt = link.type || 'CALLS';

      if (lt === 'DARK_FORCE') {
        let darkE = null;
        let fileE = null;
        if (sa.isDark && tb.file) {
          darkE = sa;
          fileE = tb;
        } else if (tb.isDark && sa.file) {
          darkE = tb;
          fileE = sa;
        }
        if (darkE && fileE && dirname(fileE.file) === dirId) {
          incoming++;
          connections.push({
            direction: '⚡',
            name: darkE.label || '?',
            dir: '',
            type: 'DARK',
          });
        }
        continue;
      }

      if (sIn && !tIn) {
        outgoing++;
        connections.push({
          direction: '→',
          name: tb.label || '?',
          dir: tb.dir != null ? tb.dir : '',
          type: lt,
        });
      } else {
        incoming++;
        connections.push({
          direction: '←',
          name: sa.label || '?',
          dir: sa.dir != null ? sa.dir : '',
          type: lt,
        });
      }
    }

    const uniqueConnections = [];
    const seen = new Set();
    for (const c of connections) {
      const key = c.direction + '\0' + c.name + '\0' + c.type + '\0' + c.dir;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueConnections.push(c);
      }
    }
    const topConnections = uniqueConnections.slice(0, 15);

    const maxComplexity = 500;
    const complexity = Math.min(100, Math.round((totalFunctions / maxComplexity) * 100));
    const connectivity = Math.min(100, Math.round(((incoming + outgoing) / 100) * 100));

    const entangledCount = rawLinks.filter(l => {
      if (l.type !== 'ENTANGLED') return false;
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      const sa = xrayEndpoint(sid, nodeById);
      const tb = xrayEndpoint(tid, nodeById);
      return sa.dir === dirId || tb.dir === dirId;
    }).length;
    const entanglementRisk = Math.min(100, entangledCount * 10);

    const darkForceCount = rawLinks.filter(l => {
      if (l.type !== 'DARK_FORCE') return false;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      const tb = xrayEndpoint(tid, nodeById);
      return tb.dir === dirId;
    }).length;

    const issues = detectIssues(dirId, filesBase, incoming, outgoing, entangledCount, darkForceCount, rawLinks);

    const diagnosticsHTML =
      issues.length > 0
        ? `
  <div style="margin-bottom: 20px;">
    <div style="font-size: 12px; color: #ef4444; letter-spacing: 1px; margin-bottom: 10px; font-weight: 600;">
      DIAGNOSTICS (${issues.length} issue${issues.length !== 1 ? 's' : ''})
    </div>
    ${issues
      .map(
        issue => `
      <div style="
        background: rgba(${issue.severity === 'high' ? '239,68,68' : issue.severity === 'med' ? '245,158,11' : '74,222,128'}, 0.06);
        border-left: 3px solid ${issue.severity === 'high' ? '#ef4444' : issue.severity === 'med' ? '#f59e0b' : '#4ade80'};
        border-radius: 0 6px 6px 0;
        padding: 8px 10px;
        margin-bottom: 6px;
      ">
        <div style="font-size: 12px; color: #e2e8f0; font-weight: 500;">
          ${issue.icon} ${escapeHtml(issue.title)}
        </div>
        <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">
          ${escapeHtml(issue.detail)}
        </div>
        <div style="font-size: 10px; color: #6366f1; margin-top: 4px; font-style: italic;">
          💡 ${escapeHtml(issue.fix)}
        </div>
      </div>
    `
      )
      .join('')}
  </div>
`
        : `
  <div style="margin-bottom: 20px;">
    <div style="font-size: 12px; color: #4ade80; letter-spacing: 1px; margin-bottom: 8px; font-weight: 600;">
      DIAGNOSTICS
    </div>
    <div style="font-size: 12px; color: #4ade80; padding: 8px 10px; background: rgba(74,222,128,0.06); border-radius: 6px;">
      ✅ No issues detected — this module looks healthy
    </div>
  </div>
`;

    const typeColors = {
      CALLS: '#4ade80',
      IMPORTS: '#f97316',
      IMPORT: '#f97316',
      DEFINES: '#3b82f6',
      ENTANGLED: '#f59e0b',
      DARK_FORCE: '#8b5cf6',
      DARK: '#8b5cf6',
    };

    const filesHtml = filesBase.slice(0, 12).map(f => {
      const ext = (f.name || '').toLowerCase();
      const dotColor = ext.endsWith('.py') ? '#3b82f6' : ext.endsWith('.ts') || ext.endsWith('.tsx') || ext.endsWith('.js') ? '#06b6d4' : '#8b5cf6';
      const nm = f.name || '';
      const disp = nm.length > 28 ? nm.slice(0, 26) + '…' : nm;
      return (
        '<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid rgba(99,102,241,0.08);">' +
        '<span style="font-size: 12px; color: #e2e8f0; font-family: \'JetBrains Mono\', monospace;">' +
        '<span style="color: ' + dotColor + ';">●</span> ' + escapeHtml(disp) +
        '</span>' +
        '<span style="font-size: 11px; color: #4ade80;">⚡' + (f.symbolCount || 0) + '</span>' +
        '</div>'
      );
    }).join('');

    const connRows = topConnections.map(c => {
      const nm = c.name.length > 24 ? c.name.slice(0, 22) + '…' : c.name;
      const tc = typeColors[c.type] || '#64748b';
      return (
        '<div style="display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid rgba(99,102,241,0.05);">' +
        '<span style="font-size: 11px; color: #94a3b8;">' + escapeHtml(c.direction + ' ' + nm) + '</span>' +
        '<span style="font-size: 10px; color: ' + tc + '; font-family: \'JetBrains Mono\', monospace;">' + escapeHtml(c.type) + '</span>' +
        '</div>'
      );
    }).join('');

    return (
      '<div style="margin-bottom: 20px;">' +
      '<div style="font-family: \'Syne\', sans-serif; font-size: 13px; color: #6366f1; letter-spacing: 2px; margin-bottom: 4px;">X-RAY</div>' +
      '<div style="font-size: 18px; font-weight: 600; color: #fff;">' + escapeHtml(dirName) + '</div>' +
      '<div style="font-size: 12px; color: #64748b; margin-top: 2px;">' + escapeHtml(dirId || '·') + '</div>' +
      '</div>' +
      '<div style="display: flex; gap: 16px; margin-bottom: 20px;">' +
      '<div style="background: rgba(99,102,241,0.1); border-radius: 8px; padding: 10px 14px; flex:1;">' +
      '<div style="font-size: 20px; font-weight: 700; color: #6366f1;">' + filesBase.length + '</div>' +
      '<div style="font-size: 11px; color: #64748b;">files</div></div>' +
      '<div style="background: rgba(74,222,128,0.1); border-radius: 8px; padding: 10px 14px; flex:1;">' +
      '<div style="font-size: 20px; font-weight: 700; color: #4ade80;">' + totalFunctions + '</div>' +
      '<div style="font-size: 11px; color: #64748b;">functions</div></div>' +
      '<div style="background: rgba(245,158,11,0.1); border-radius: 8px; padding: 10px 14px; flex:1;">' +
      '<div style="font-size: 20px; font-weight: 700; color: #f59e0b;">' + (incoming + outgoing) + '</div>' +
      '<div style="font-size: 11px; color: #64748b;">connections</div></div>' +
      '</div>' +
      '<div style="margin-bottom: 20px;">' +
      '<div style="font-size: 12px; color: #6366f1; letter-spacing: 1px; margin-bottom: 8px; font-weight: 600;">FILES (by connections)</div>' +
      filesHtml +
      (filesBase.length > 12 ? '<div style="font-size: 11px; color: #64748b; padding: 4px 0;">…' + (filesBase.length - 12) + ' more</div>' : '') +
      '</div>' +
      '<div style="margin-bottom: 20px;">' +
      '<div style="font-size: 12px; color: #6366f1; letter-spacing: 1px; margin-bottom: 8px; font-weight: 600;">CONNECTIONS</div>' +
      '<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">' +
      '<span style="font-size: 11px; color: #4ade80;">→ ' + outgoing + ' outgoing</span>' +
      '<span style="font-size: 11px; color: #f97316;">← ' + incoming + ' incoming</span>' +
      (darkForceCount > 0 ? '<span style="font-size: 11px; color: #8b5cf6;">⚡ ' + darkForceCount + ' dark</span>' : '') +
      '</div>' +
      connRows +
      '</div>' +
      diagnosticsHTML +
      '<div>' +
      '<div style="font-size: 12px; color: #6366f1; letter-spacing: 1px; margin-bottom: 10px; font-weight: 600;">HEALTH</div>' +
      buildHealthBar('Complexity', complexity, '#6366f1') +
      buildHealthBar('Connectivity', connectivity, '#4ade80') +
      buildHealthBar('Entanglement risk', entanglementRisk, '#f59e0b') +
      '</div>' +
      buildXrayAiSection(dirId)
    );
  }

  function buildXrayAiSection(dirId) {
    const djs = JSON.stringify(dirId == null ? '' : String(dirId));
    if (aiAvailable) {
      return (
        '<div style="margin-top: 20px; border-top: 1px solid rgba(99,102,241,0.2); padding-top: 16px;">' +
        '<div style="font-size: 12px; color: #a855f7; letter-spacing: 1px; margin-bottom: 10px; font-weight: 600;">' +
        '🧠 AI AGENT <span style="font-size: 10px; color: #64748b; font-weight: 400;">(' +
        escapeHtml(aiProvider) +
        ')</span></div>' +
        '<div style="display: flex; flex-direction: column; gap: 6px;">' +
        '<button type="button" onclick="runAIDiagnose(' +
        djs +
        ')" style="' +
        "background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.3);" +
        "color: #a855f7; padding: 8px 12px; border-radius: 6px; cursor: pointer;" +
        "font-family: 'Outfit', sans-serif; font-size: 12px; text-align: left;" +
        '">🔍 Diagnose Issues</button>' +
        '<button type="button" onclick="runAISecurity(' +
        djs +
        ')" style="' +
        "background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);" +
        "color: #ef4444; padding: 8px 12px; border-radius: 6px; cursor: pointer;" +
        "font-family: 'Outfit', sans-serif; font-size: 12px; text-align: left;" +
        '">🛡️ Security Scan</button>' +
        '<button type="button" onclick="runAIArchitecture()" style="' +
        "background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3);" +
        "color: #3b82f6; padding: 8px 12px; border-radius: 6px; cursor: pointer;" +
        "font-family: 'Outfit', sans-serif; font-size: 12px; text-align: left;" +
        '">🏗️ Explain Architecture</button>' +
        '</div>' +
        '<div style="margin-top: 10px;">' +
        '<div style="display: flex; gap: 6px;">' +
        '<input type="text" id="ai-question-input" placeholder="Ask about this module..." ' +
        'style="flex:1; background: rgba(10,15,26,0.8); border: 1px solid rgba(99,102,241,0.2); ' +
        'color: #e2e8f0; padding: 6px 10px; border-radius: 6px; font-size: 12px; ' +
        'font-family: \'Outfit\', sans-serif; outline: none;" />' +
        '<button type="button" onclick="runAIAsk(' +
        djs +
        ')" style="' +
        "background: rgba(99,102,241,0.2); border: 1px solid rgba(99,102,241,0.3);" +
        "color: #6366f1; padding: 6px 12px; border-radius: 6px; cursor: pointer;" +
        'font-size: 12px;">Ask</button>' +
        '</div></div>' +
        '<div id="ai-response" style="margin-top: 10px;"></div>' +
        '</div>'
      );
    }
    return (
      '<div style="margin-top: 20px; border-top: 1px solid rgba(99,102,241,0.1); padding-top: 12px;">' +
      '<div style="font-size: 11px; color: #64748b;">' +
      '🧠 AI Agent unavailable — set OMNIX_AI_KEY or install Ollama' +
      '</div></div>'
    );
  }

  function showAILoading(message) {
    const el = document.getElementById('ai-response');
    if (!el) return;
    el.innerHTML =
      '<div style="color: #a855f7; font-size: 12px; padding: 8px;">' +
      '<span style="display: inline-block; animation: pulse 1s infinite;">⏳</span> ' +
      escapeHtml(message) +
      '</div>';
  }

  function startAITraceAnimation(dirId) {
    aiTraceActive = true;
    aiTraceTarget = dirId;
    if (window._aiTraceGfx) {
      window._aiTraceGfx.alpha = 1;
    }
  }

  function stopAITraceAnimation() {
    aiTraceActive = false;
    aiTraceTarget = null;
    if (window._aiTraceGfx) {
      gsap.killTweensOf(window._aiTraceGfx);
      window._aiTraceGfx.clear();
      window._aiTraceGfx.alpha = 1;
    }
  }

  function buildAITraceSummaryHTML(trace) {
    if (!trace) return '';
    const ne = trace.nodes_examined || [];
    const ef = trace.edges_followed || [];
    if (ne.length === 0 && ef.length === 0) return '';
    const chain = ne
      .slice(0, 5)
      .map(f => escapeHtml(basename(f)))
      .join(' → ');
    return (
      '<div style="margin-top: 8px; padding: 6px 8px; background: rgba(168,85,247,0.08); border-radius: 4px;">' +
      '<div style="font-size: 10px; color: #a855f7; margin-bottom: 4px;">' +
      '🧠 Reasoning Trail: examined ' +
      ne.length +
      ' files, followed ' +
      ef.length +
      ' connections' +
      '</div>' +
      (chain
        ? '<div style="font-size: 9px; color: #64748b;">' +
          chain +
          (ne.length > 5 ? ' → ...' : '') +
          '</div>'
        : '') +
      '</div>'
    );
  }

  function flashNode(simNode, color, intensity) {
    if (!simNode) return;
    const idx = simNodes.indexOf(simNode);
    if (idx < 0) return;
    const pool = nodePool[idx];
    if (!pool || !pool.container) return;

    const flash = new PIXI.Graphics();
    flash.lineStyle(3, color, 0.8);
    flash.drawCircle(0, 0, (simNode.radius || 18) * intensity);
    flash.position.set(0, 0);
    pool.container.addChild(flash);

    gsap.fromTo(
      flash.scale,
      { x: 0.5, y: 0.5 },
      { x: 2, y: 2, duration: 0.8, ease: 'power2.out' }
    );
    gsap.fromTo(
      flash,
      { alpha: 1 },
      {
        alpha: 0,
        duration: 0.8,
        ease: 'power2.out',
        onComplete: () => {
          if (flash.parent) flash.parent.removeChild(flash);
          flash.destroy({ children: true });
        },
      }
    );

    if (pool.glow) {
      const origAlpha = pool.glow.alpha;
      gsap.to(pool.glow, {
        alpha: 1,
        duration: 0.3,
        yoyo: true,
        repeat: 1,
        ease: 'power2.inOut',
        onComplete: () => {
          pool.glow.alpha = origAlpha;
        },
      });
    }

    gsap.to(pool.container.scale, {
      x: 1.3,
      y: 1.3,
      duration: 0.2,
      yoyo: true,
      repeat: 1,
      ease: 'back.out(2)',
      onComplete: () => {
        pool.container.scale.set(1, 1);
      },
    });
  }

  studio._flashNodeRim = function (nodeId, opts) {
    opts = opts || {};
    const color = opts.color != null ? opts.color : 0xffffff;
    const ms = opts.durationMs != null ? opts.durationMs : 200;
    const pc =
      world &&
      world.children &&
      world.children.find(c => c._omnixType === 'planet');
    if (!pc || !pc._nodes) return;
    let pnRef = null;
    for (let pi = 0; pi < pc._nodes.length; pi++) {
      const pn = pc._nodes[pi];
      if (pn && pn.symbol && pn.symbol.id === nodeId) {
        pnRef = pn;
        break;
      }
    }
    if (!pnRef || !pnRef.container) return;
    const radius = pnRef.radius || 18;
    const rim = new PIXI.Graphics();
    rim.lineStyle(2, color, 1.0);
    rim.drawCircle(0, 0, radius * 1.15);
    pnRef.container.addChild(rim);
    gsap.to(rim, {
      alpha: 0,
      duration: ms / 1000,
      ease: 'sine.out',
      onComplete: () => {
        if (rim.parent) rim.parent.removeChild(rim);
        rim.destroy({ children: true });
      },
    });
  };

  studio._fadeAndRemoveNode = function (nodeId, opts) {
    opts = opts || {};
    const ms = opts.durationMs != null ? opts.durationMs : 400;

    const planetLayer = world.children.find(c => c._omnixType === 'planet');
    if (!planetLayer || !planetLayer._nodes) return;

    let pnRef = null;
    for (let i = 0; i < planetLayer._nodes.length; i++) {
      const pn = planetLayer._nodes[i];
      if (pn && pn.symbol && pn.symbol.id === nodeId) {
        pnRef = pn;
        break;
      }
    }
    if (!pnRef || !pnRef.container) return;

    gsap.killTweensOf(pnRef.container);
    gsap.to(pnRef.container, {
      alpha: 0,
      duration: ms / 1000,
      ease: 'power2.out',
      onComplete: () => {
        const currentPlanet = world.children.find(c => c._omnixType === 'planet');
        if (currentPlanet && currentPlanet._nodes) {
          const stillIdx = currentPlanet._nodes.indexOf(pnRef);
          if (stillIdx !== -1) {
            currentPlanet._nodes.splice(stillIdx, 1);
          }
        }
        if (pnRef.container) {
          if (pnRef.container.parent) {
            pnRef.container.parent.removeChild(pnRef.container);
          }
          pnRef.container.destroy({ children: true });
        }
      },
    });
  };

  studio._bornNode = function (_wsId, nodeData, opts) {
    opts = opts || {};
    const ms = opts.durationMs != null ? opts.durationMs : 400;
    if (!nodeData || typeof nodeData.id !== 'string') return false;
    if (viewLevel !== 'planet' || !selectedFile) return false;
    const t = typeof nodeData.type === 'string' ? nodeData.type : '';
    if (t !== 'function' && t !== 'class' && t !== 'method') return false;
    const nodeFile = typeof nodeData.file === 'string' ? nodeData.file : '';
    const selFp = selectedFile.filePath || '';
    if (nodeFile && selFp && nodeFile !== selFp) return false;

    const planetLayer = world && world.children && world.children.find(c => c._omnixType === 'planet');
    if (!planetLayer || !planetLayer._nodes || !planetLayer._sim) return false;
    if (planetLayer._nodes.length >= 100) return false;

    const sym = {
      id: nodeData.id,
      name: typeof nodeData.name === 'string' ? nodeData.name : '',
      type: t,
      line: typeof nodeData.line === 'number' ? nodeData.line : 0,
      complexity:
        typeof nodeData.val === 'number' && nodeData.val > 0 ? nodeData.val : 1,
    };
    for (let di = 0; di < planetLayer._nodes.length; di++) {
      const prev = planetLayer._nodes[di];
      if (prev && prev.symbol && prev.symbol.id === sym.id) return false;
    }

    const fileData = selectedFile;
    const fp = fileData.filePath || resolveDirFilePath(selectedDir, fileData.name);
    const centerX = planetLayer._planetCenterX != null
      ? planetLayer._planetCenterX
      : app.screen.width / 2;
    const centerY = planetLayer._planetCenterY != null
      ? planetLayer._planetCenterY
      : app.screen.height / 2;

    const val = sym.complexity != null && sym.complexity > 0 ? sym.complexity : 1;
    const radius = Math.sqrt(val) * 4 + 8;
    const classification = classifyPlanetSymbol(sym);
    const color = classification.color;

    const jx = centerX + (Math.random() - 0.5) * 140;
    const jy = centerY + (Math.random() - 0.5) * 140;
    const j = planetLayer._nodes.length;

    const symContainer = new PIXI.Container();
    symContainer.position.set(jx, jy);
    symContainer.alpha = 0;
    symContainer.scale.set(0, 0);
    symContainer.eventMode = 'static';
    symContainer.cursor = 'pointer';

    const glow = new PIXI.Graphics();
    glow.beginFill(color, 0.12);
    glow.drawCircle(0, 0, radius * 2.5);
    glow.endFill();
    glow.alpha = 0.55;
    symContainer.addChild(glow);

    const cellFill = new PIXI.Graphics();
    cellFill.beginFill(color, 0.25);
    cellFill.drawCircle(0, 0, radius);
    cellFill.endFill();
    symContainer.addChild(cellFill);

    const membraneGfx = new PIXI.Graphics();
    symContainer.addChild(membraneGfx);

    const nucleus = new PIXI.Graphics();
    nucleus.beginFill(color, 0.9);
    nucleus.drawCircle(0, 0, 3);
    nucleus.endFill();
    symContainer.addChild(nucleus);

    const rawName = sym.name || '';
    const nm =
      rawName.length > 20 ? rawName.slice(0, 18) + '…' : rawName;
    const label = new PIXI.Text(nm, {
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 11,
      fill: 0xe2e8f0,
      align: 'center',
    });
    label.alpha = 0.8;
    label.anchor.set(0.5, 0);
    label.position.set(0, radius + 5);
    label.eventMode = 'none';
    label.visible = radius > 12;
    symContainer.addChild(label);

    const symHitR = Math.max(radius * 2.8, radius + 36);
    symContainer.hitArea = new PIXI.Circle(0, 0, symHitR);

    planetLayer.addChild(symContainer);

    const pnRef = {
      container: symContainer,
      symbol: sym,
      x: jx,
      y: jy,
      vx: 0,
      vy: 0,
      radius,
      color,
      classification,
      glow,
      cellFill,
      membraneGfx,
      nucleus,
      label,
      index: j,
      _hover: false,
    };

    symContainer.on('pointerdown', e => {
      const btn = pointerEventButton(e);
      if (btn === 2) {
        e.stopPropagation();
        const oe = e.data && e.data.originalEvent;
        if (oe && oe.preventDefault) oe.preventDefault();
        void openXrayForPlanetFunction(fileData, sym, classification, fp);
        return;
      }
      if (btn !== 0) return;
      e.stopPropagation();
      if (
        (sym.type === 'function' || sym.type === 'class' || sym.type === 'method') &&
        typeof studio._options.onFunctionNodeClick === 'function' &&
        sym &&
        sym.id
      ) {
        try {
          studio._options.onFunctionNodeClick(String(sym.id));
        } catch (_e) { /* */ }
        return;
      }
      showSymbolDetailPopup(sym, fileData);
    });
    symContainer.on('pointerover', () => {
      pnRef._hover = true;
      gsap.to(symContainer.scale, { x: 1.2, y: 1.2, duration: 0.2 });
    });
    symContainer.on('pointerout', () => {
      pnRef._hover = false;
      gsap.to(symContainer.scale, { x: 1, y: 1, duration: 0.2 });
    });

    planetLayer._nodes.push(pnRef);
    planetNodes = planetLayer._nodes;

    planetLayer._sim.nodes(planetLayer._nodes).alpha(0.3).restart();

    gsap.killTweensOf(symContainer);
    gsap.killTweensOf(symContainer.scale);
    const bornTl = gsap.timeline({
      onComplete: () => {
        delete symContainer._omnixBornTween;
        symContainer.alpha = 1;
        symContainer.scale.set(1, 1);
        symContainer.eventMode = 'static';
      },
    });
    symContainer._omnixBornTween = bornTl;
    bornTl.to(
      symContainer,
      {
        alpha: 1,
        duration: ms / 1000,
        ease: 'power2.out',
      },
      0
    );
    bornTl.to(
      symContainer.scale,
      {
        x: 1,
        y: 1,
        duration: ms / 1000,
        ease: 'power2.out',
      },
      0
    );

    return true;
  };

  /** T2 v2 slice 6a — live edge_added: CALLS link between existing planet cells (synth ids). */
  studio._bornEdge = function (fromSynthId, toSynthId) {
    if (!fromSynthId || !toSynthId || fromSynthId === toSynthId) return false;
    if (viewLevel !== 'planet' || !selectedFile) return false;

    const planetLayer =
      world && world.children && world.children.find(c => c._omnixType === 'planet');
    if (!planetLayer || !planetLayer._nodes || !planetLayer._sim || !planetLayer._edges)
      return false;

    let fromPn = null;
    let toPn = null;
    for (let i = 0; i < planetLayer._nodes.length; i++) {
      const pn = planetLayer._nodes[i];
      if (!pn || !pn.symbol) continue;
      if (pn.symbol.id === fromSynthId) fromPn = pn;
      if (pn.symbol.id === toSynthId) toPn = pn;
      if (fromPn && toPn) break;
    }
    if (!fromPn || !toPn) {
      // eslint-disable-next-line no-console
      console.debug('[t2-slice6a] _bornEdge missing pnRef for endpoint', {
        fromSynthId,
        toSynthId,
      });
      return false;
    }

    function pairKey(a, b) {
      return a < b ? a + ':' + b : b + ':' + a;
    }
    const newKey = pairKey(fromSynthId, toSynthId);
    const edges = planetLayer._edges;
    for (let ei = 0; ei < edges.length; ei++) {
      const ed = edges[ei];
      const s = ed.source;
      const t = ed.target;
      if (!s || !t || !s.symbol || !t.symbol) continue;
      const sid = s.symbol.id;
      const tid = t.symbol.id;
      if (pairKey(sid, tid) === newKey) {
        // eslint-disable-next-line no-console
        console.debug('[t2-slice6a] _bornEdge duplicate unordered pair', newKey);
        return false;
      }
    }

    edges.push({
      source: fromPn,
      target: toPn,
      type: 'CALLS',
      color: 0x4ade80,
      _curveOffset: (Math.random() - 0.5) * 36,
    });

    planetLayer._sim.force('link').links(edges);
    planetLayer._sim.alpha(0.3).restart();

    return true;
  };

  function drawTraceLine(gfx, fromNode, toNode, index) {
    const color = 0xa855f7;
    const alpha = Math.max(0.12, 0.55 - index * 0.05);
    const sx = fromNode.x;
    const sy = fromNode.y;
    const tx = toNode.x;
    const ty = toNode.y;
    const midX = (sx + tx) / 2 + ((index % 3) - 1) * 24;
    const midY = (sy + ty) / 2 - 20;
    gfx.lineStyle(2, color, alpha);
    gfx.moveTo(sx, sy);
    gfx.quadraticCurveTo(midX, midY, tx, ty);
    gfx.beginFill(color, alpha);
    gfx.drawCircle(tx, ty, 4);
    gfx.endFill();
    gfx.lineStyle(0);
  }

  function pulseGalaxyEdgeForTrace(edge) {
    if (!edge || viewLevel !== 'galaxy') return;
    const fromSn = findSimDirForGraphNode(edge.from);
    const toSn = findSimDirForGraphNode(edge.to);
    if (!fromSn || !toSn || fromSn === toSn) return;
    const idA = fromSn.id;
    const idB = toSn.id;
    const key = idA < idB ? idA + '\0' + idB : idB + '\0' + idA;
    traceEdgePulseUntil.set(key, performance.now() + 900);
  }

  function animateAITrace(traceData) {
    if (!traceData || viewLevel !== 'galaxy' || !world || !app) return;
    const traceGfx = window._aiTraceGfx;
    if (!traceGfx) return;

    const runId = ++aiTraceRunId;
    gsap.killTweensOf(traceGfx);
    traceGfx.clear();
    traceGfx.alpha = 1;

    const nodesExamined = traceData.nodes_examined || [];
    const edgesFollowed = traceData.edges_followed || [];
    const targetDir = traceData.directory || '';

    const matchedNodes = [];
    const seen = new Set();
    const cap = Math.min(10, nodesExamined.length);
    for (let i = 0; i < cap; i++) {
      const node = findGalaxyDirSimNodeForFilePath(nodesExamined[i]);
      if (node && !seen.has(node.id)) {
        seen.add(node.id);
        matchedNodes.push(node);
      }
    }

    let targetNode = findGalaxyDirSimNodeForDirPath(targetDir);
    if (!targetNode && xrayDirId) {
      targetNode = findGalaxyDirSimNodeForDirPath(xrayDirId);
    }

    let delay = 0;
    const STEP_DELAY = 0.4;

    if (targetNode) {
      gsap.delayedCall(delay, () => {
        if (runId !== aiTraceRunId) return;
        flashNode(targetNode, 0xa855f7, 2.0);
      });
      delay += STEP_DELAY;
    }

    for (let i = 0; i < matchedNodes.length; i++) {
      const node = matchedNodes[i];
      const di = i;
      gsap.delayedCall(delay, () => {
        if (runId !== aiTraceRunId) return;
        flashNode(node, 0x4ade80, 1.5);
        if (targetNode) drawTraceLine(traceGfx, targetNode, node, di);
      });
      delay += STEP_DELAY;
    }

    const edgeCap = Math.min(10, edgesFollowed.length);
    for (let j = 0; j < edgeCap; j++) {
      const ej = edgesFollowed[j];
      const tEdge = j * 0.15;
      gsap.delayedCall(tEdge, () => {
        if (runId !== aiTraceRunId) return;
        pulseGalaxyEdgeForTrace(ej);
      });
    }

    gsap.delayedCall(delay + 2, () => {
      if (runId !== aiTraceRunId) return;
      gsap.to(traceGfx, {
        alpha: 0,
        duration: 3,
        ease: 'power2.out',
        onComplete: () => {
          if (runId !== aiTraceRunId) return;
          traceGfx.clear();
          traceGfx.alpha = 1;
        },
      });
    });
  }

  function renderAIResponse(data) {
    const el = document.getElementById('ai-response');
    if (!el) return;

    if (data.error) {
      el.innerHTML =
        '<div style="color: #ef4444; font-size: 12px; padding: 8px;">❌ ' +
        escapeHtml(String(data.error)) +
        '</div>';
      return;
    }

    if (data.diagnosis) {
      const d = data.diagnosis;
      const severityColor =
        d.severity === 'high' ? '#ef4444' : d.severity === 'medium' ? '#f59e0b' : '#4ade80';
      const steps = (data.reasoning_steps || [])
        .map(s => '<div style="font-size: 10px; color: #64748b; padding: 2px 0;">→ ' + escapeHtml(String(s)) + '</div>')
        .join('');
      const fixes = (data.fixes || [])
        .map(
          (f, i) =>
            '<div style="margin-top: 8px; background: rgba(74,222,128,0.05); border-left: 2px solid #4ade80; padding: 8px; border-radius: 0 4px 4px 0;">' +
            '<div style="font-size: 12px; color: #4ade80; font-weight: 500;">Fix ' +
            (i + 1) +
            ': ' +
            escapeHtml(String(f.title || '')) +
            '</div>' +
            '<div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">' +
            escapeHtml(String(f.description || '')) +
            '</div>' +
            (f.code_changes
              ? '<pre style="font-size: 10px; color: #e2e8f0; background: rgba(0,0,0,0.3); padding: 6px; border-radius: 4px; margin-top: 4px; overflow-x: auto; font-family: \'JetBrains Mono\', monospace;">' +
                escapeHtml(String(f.code_changes)) +
                '</pre>'
              : '') +
            '<div style="font-size: 10px; color: #64748b; margin-top: 2px;">Risk: ' +
            escapeHtml(String(f.risk || '?')) +
            ' · Effort: ' +
            escapeHtml(String(f.effort || '?')) +
            '</div></div>'
        )
        .join('');
      el.innerHTML =
        '<div style="background: rgba(168,85,247,0.05); border-radius: 8px; padding: 12px; margin-top: 8px;">' +
        '<div style="font-size: 13px; color: #e2e8f0; font-weight: 600; margin-bottom: 6px;">' +
        escapeHtml(String(d.summary || '')) +
        '</div>' +
        '<div style="font-size: 11px; color: #94a3b8; margin-bottom: 8px;">' +
        escapeHtml(String(d.root_cause || '')) +
        '</div>' +
        '<div style="display: flex; gap: 8px; margin-bottom: 8px;">' +
        '<span style="font-size: 10px; color: ' +
        severityColor +
        '; background: ' +
        severityColor +
        '22; padding: 2px 8px; border-radius: 4px;">' +
        escapeHtml(String(d.severity || 'unknown')) +
        '</span>' +
        '<span style="font-size: 10px; color: #a855f7; background: rgba(168,85,247,0.1); padding: 2px 8px; border-radius: 4px;">Confidence: ' +
        escapeHtml(String(d.confidence != null ? d.confidence : 0)) +
        '%</span></div>' +
        steps +
        fixes +
        buildAITraceSummaryHTML(data.trace) +
        '</div>' +
        '<div style="font-size: 10px; color: #64748b; margin-top: 6px;">via ' +
        escapeHtml(String(data.provider || 'unknown')) +
        '</div>';
      if (data.trace) animateAITrace(data.trace);
      return;
    }

    if (data.answer) {
      el.innerHTML =
        '<div style="background: rgba(99,102,241,0.05); border-radius: 8px; padding: 12px; margin-top: 8px;">' +
        '<div style="font-size: 12px; color: #e2e8f0; white-space: pre-wrap;">' +
        escapeHtml(String(data.answer)) +
        '</div>' +
        buildAITraceSummaryHTML(data.trace) +
        '<div style="font-size: 10px; color: #64748b; margin-top: 6px;">via ' +
        escapeHtml(String(data.provider || 'unknown')) +
        '</div></div>';
      if (data.trace) animateAITrace(data.trace);
      return;
    }

    if (data.vulnerabilities) {
      const vulns = (data.vulnerabilities || [])
        .map(v => {
          const border =
            v.severity === 'critical'
              ? '#ef4444'
              : v.severity === 'high'
                ? '#f59e0b'
                : '#4ade80';
          return (
            '<div style="margin-top: 6px; padding: 6px; border-left: 2px solid ' +
            border +
            '; background: rgba(0,0,0,0.2); border-radius: 0 4px 4px 0;">' +
            '<div style="font-size: 11px; color: #e2e8f0;">' +
            escapeHtml(String(v.type || '')) +
            ': ' +
            escapeHtml(String(v.description || '')) +
            '</div>' +
            '<div style="font-size: 10px; color: #64748b;">' +
            escapeHtml(String(v.file || '')) +
            (v.line ? ':' + escapeHtml(String(v.line)) : '') +
            ' · ' +
            escapeHtml(String(v.cwe || '')) +
            '</div>' +
            '<div style="font-size: 10px; color: #4ade80; margin-top: 2px;">💡 ' +
            escapeHtml(String(v.fix || '')) +
            '</div></div>'
          );
        })
        .join('');
      el.innerHTML =
        '<div style="background: rgba(239,68,68,0.05); border-radius: 8px; padding: 12px; margin-top: 8px;">' +
        '<div style="font-size: 13px; color: #ef4444; font-weight: 600; margin-bottom: 6px;">🛡️ ' +
        escapeHtml(String(data.scan_summary || 'Security Scan Complete')) +
        '</div>' +
        vulns +
        buildAITraceSummaryHTML(data.trace) +
        '</div>' +
        '<div style="font-size: 10px; color: #64748b; margin-top: 6px;">via ' +
        escapeHtml(String(data.provider || 'unknown')) +
        '</div>';
      if (data.trace) animateAITrace(data.trace);
      return;
    }

    el.innerHTML =
      '<div style="font-size: 12px; color: #e2e8f0; padding: 8px; white-space: pre-wrap;">' +
      escapeHtml(JSON.stringify(data, null, 2)) +
      '</div>';
  }

  async function runAIDiagnose(dirId) {
    startAITraceAnimation(dirId);
    showAILoading('Diagnosing issues...');
    try {
      const resp = await fetch('/api/ai/diagnose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: dirId }),
      });
      const data = await resp.json();
      stopAITraceAnimation();
      renderAIResponse(data);
    } catch (e) {
      stopAITraceAnimation();
      renderAIResponse({ error: e.message });
    }
  }

  async function runAISecurity(dirId) {
    startAITraceAnimation(dirId);
    showAILoading('Running security scan...');
    try {
      const resp = await fetch('/api/ai/security', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: dirId }),
      });
      const data = await resp.json();
      stopAITraceAnimation();
      renderAIResponse(data);
    } catch (e) {
      stopAITraceAnimation();
      renderAIResponse({ error: e.message });
    }
  }

  async function runAIArchitecture() {
    showAILoading('Analyzing architecture...');
    try {
      const resp = await fetch('/api/ai/architecture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await resp.json();
      renderAIResponse(data);
    } catch (e) {
      renderAIResponse({ error: e.message });
    }
  }

  async function runAIAsk(dirId) {
    const input = document.getElementById('ai-question-input');
    const question = input ? input.value.trim() : '';
    if (!question) return;
    startAITraceAnimation(dirId);
    showAILoading('Thinking...');
    try {
      const resp = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, directory: dirId }),
      });
      const data = await resp.json();
      stopAITraceAnimation();
      renderAIResponse(data);
    } catch (e) {
      stopAITraceAnimation();
      renderAIResponse({ error: e.message });
    }
  }

  window.runAIDiagnose = runAIDiagnose;
  window.runAISecurity = runAISecurity;
  window.runAIArchitecture = runAIArchitecture;
  window.runAIAsk = runAIAsk;

  function buildXrayFunctionHTML(fileData, sym, classification, filePath) {
    const nm = sym.name || '?';
    const lineStr = sym.line != null && sym.line !== '' ? String(sym.line) : '—';
    const valStr =
      sym.complexity != null && sym.complexity !== '' ? String(sym.complexity) : '—';
    const conn = countSymbolConnections(sym.id, filePath);
    const typeChip =
      '<span style="display:inline-block;padding:4px 10px;border-radius:6px;font-size:11px;background:rgba(99,102,241,0.15);color:#a5b4fc;border:1px solid rgba(99,102,241,0.35);">' +
      escapeHtml(classification.label) +
      '</span>';
    return (
      '<div style="margin-bottom: 18px;">' +
      '<div style="font-family: \'Syne\', sans-serif; font-size: 13px; color: #6366f1; letter-spacing: 2px; margin-bottom: 4px;">X-RAY · SYMBOL</div>' +
      '<div style="font-size: 18px; font-weight: 600; color: #fff; word-break: break-word;">' +
      escapeHtml(nm) +
      '</div>' +
      '<div style="font-size: 12px; color: #64748b; margin-top: 6px; font-family: \'JetBrains Mono\', monospace; word-break: break-all;">' +
      escapeHtml(fileData.name || '') +
      '</div></div>' +
      '<div style="display: flex; flex-direction: column; gap: 12px;">' +
      '<div><div style="font-size: 10px; color: #64748b; letter-spacing: 1px; margin-bottom: 4px;">LINE</div>' +
      '<div style="font-size: 14px; color: #e2e8f0; font-family: \'JetBrains Mono\', monospace;">' +
      escapeHtml(lineStr) +
      '</div></div>' +
      '<div><div style="font-size: 10px; color: #64748b; letter-spacing: 1px; margin-bottom: 4px;">COMPLEXITY (VAL)</div>' +
      '<div style="font-size: 14px; color: #4ade80; font-family: \'JetBrains Mono\', monospace;">' +
      escapeHtml(valStr) +
      '</div></div>' +
      '<div><div style="font-size: 10px; color: #64748b; letter-spacing: 1px; margin-bottom: 4px;">TYPE</div>' +
      '<div>' +
      typeChip +
      '</div></div>' +
      '<div><div style="font-size: 10px; color: #64748b; letter-spacing: 1px; margin-bottom: 4px;">INTERNAL CALL EDGES</div>' +
      '<div style="font-size: 14px; color: #e2e8f0;">' +
      String(conn) +
      '</div></div>' +
      '</div>'
    );
  }

  async function openXrayForPlanetFunction(fileData, sym, classification, filePath) {
    const panel = document.getElementById('xray-panel');
    const content = document.getElementById('xray-content');
    if (!panel || !content) return;
    xrayDirId = selectedDir;
    xrayViewKind = 'function';
    await ensureAiStatus();
    content.innerHTML = buildXrayFunctionHTML(fileData, sym, classification, filePath);
    panel.scrollTop = 0;
    gsap.to(panel, { right: 0, duration: 0.4, ease: 'power3.out' });
    xrayOpen = true;
  }

  async function openXray(simNode) {
    const panel = document.getElementById('xray-panel');
    const content = document.getElementById('xray-content');
    if (!panel || !content) return;
    let did = simNode.dirId;
    if (did === undefined || did === null) did = simNode.raw && simNode.raw.id;
    if (did === undefined || did === null) return;

    xrayDirId = did;
    xrayViewKind = 'module';
    await ensureAiStatus();
    content.innerHTML = buildXrayHTML(simNode);
    panel.scrollTop = 0;
    gsap.to(panel, { right: 0, duration: 0.4, ease: 'power3.out' });
    xrayOpen = true;
  }

  function closeXray() {
    const panel = document.getElementById('xray-panel');
    if (!panel) return;
    gsap.to(panel, { right: -400, duration: 0.3, ease: 'power2.in' });
    xrayOpen = false;
    xrayDirId = null;
    xrayViewKind = 'module';
  }

  function openXrayForDir(dirId) {
    if (dirId === undefined || dirId === null || dirId === '') return;
    const pseudo = { dirId, raw: { id: dirId } };
    if (xrayOpen && xrayDirId === dirId) closeXray();
    else void openXray(pseudo);
  }

  function countSymbolConnections(symId, filePath) {
    let c = 0;
    const links = (rawGraphData && rawGraphData.links) || [];
    for (let li = 0; li < links.length; li++) {
      const l = links[li];
      if (l.type !== 'CALLS') continue;
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (sid !== symId && tid !== symId) continue;
      const other = sid === symId ? tid : sid;
      const on = model && model.nodeById.get(other);
      if (on && on.file === filePath) c += 1;
    }
    return c;
  }

  function hideSymbolPopup() {
    if (symbolPopupEl) symbolPopupEl.style.display = 'none';
  }

  function showSymbolDetailPopup(sym, fileData) {
    if (!symbolPopupEl) {
      symbolPopupEl = document.createElement('div');
      symbolPopupEl.id = 'omnix-symbol-popup';
      symbolPopupEl.style.cssText =
        'position:fixed;z-index:50;max-width:340px;padding:14px 16px;background:rgba(17,26,46,0.96);border:1px solid rgba(99,102,241,0.35);border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,0.5);font-family:JetBrains Mono,monospace;font-size:12px;color:#e2e8f0;display:none;';
      document.body.appendChild(symbolPopupEl);
    }
    const fp = fileData.filePath || resolveDirFilePath(fileData.dirId, fileData.name);
    const conn = sym.id ? countSymbolConnections(sym.id, fp) : 0;
    symbolPopupEl.innerHTML =
      '<div style="font-weight:600;color:#fff;margin-bottom:8px;">' +
      escapeHtml(sym.name) +
      '</div>' +
      '<div style="color:#94a3b8;font-size:11px;">' +
      escapeHtml(sym.type || '') +
      ' · line ' +
      (sym.line != null ? sym.line : '?') +
      ' · complexity ' +
      (sym.complexity != null ? sym.complexity : '—') +
      '</div>' +
      '<div style="margin-top:8px;color:#64748b;font-size:11px;">Connections: <span style="color:#4ade80">' +
      conn +
      '</span></div>' +
      '<div style="margin-top:10px;text-align:right;"><button type="button" id="omnix-symbol-popup-close" style="font-size:11px;padding:4px 10px;cursor:pointer;border-radius:6px;border:1px solid #475569;background:#1e293b;color:#e2e8f0;">Close</button></div>';
    symbolPopupEl.style.left = Math.min(window.innerWidth - 360, window.innerWidth / 2 - 170) + 'px';
    symbolPopupEl.style.top = '100px';
    symbolPopupEl.style.display = 'block';
    const btn = document.getElementById('omnix-symbol-popup-close');
    if (btn) btn.onclick = () => { symbolPopupEl.style.display = 'none'; };
  }

  function drawDarkMatterOverlay() {
    if (!app || !model || !darkMatterGfx) return;
    darkMatterGfx.clear();
    if (viewLevel !== 'galaxy') return;
    if (!darkMatterVisible || !simNodes.length) return;

    const raw = model.raw;
    const darkNodes = raw.nodes.filter(n => n.type === 'dark_matter').slice(0, MAX_DARK_MATTER_DRAW);
    const darkEdges = raw.links.filter(l => l.type === 'DARK_FORCE').slice(0, MAX_DARK_FORCE_DRAW);
    const nebulaColor = 0x8b5cf6;
    const darkPos = new Map();

    for (const dn of darkNodes) {
      const connectedDirs = darkEdges
        .filter(e => e.source === dn.id || e.target === dn.id)
        .map(e => (e.source === dn.id ? e.target : e.source));
      let cx = 0;
      let cy = 0;
      let cnt = 0;
      for (const fileId of connectedDirs) {
        const sn = findSimDirForGraphNode(fileId);
        if (sn && sn.x != null && sn.y != null) {
          cx += sn.x;
          cy += sn.y;
          cnt += 1;
        }
      }
      if (cnt === 0) continue;
      cx /= cnt;
      cy /= cnt;
      darkPos.set(dn.id, { x: cx, y: cy, cnt });

      const nebulaRadius = 40 + cnt * 15;
      darkMatterGfx.beginFill(nebulaColor, 0.03);
      darkMatterGfx.drawCircle(cx, cy, nebulaRadius * 2);
      darkMatterGfx.endFill();
      darkMatterGfx.beginFill(nebulaColor, 0.05);
      darkMatterGfx.drawCircle(cx, cy, nebulaRadius * 1.3);
      darkMatterGfx.endFill();
      darkMatterGfx.beginFill(nebulaColor, 0.08);
      darkMatterGfx.drawCircle(cx, cy, nebulaRadius * 0.7);
      darkMatterGfx.endFill();
    }

    for (const edge of darkEdges) {
      const p0 = darkPos.get(edge.source);
      const dirSn = findSimDirForGraphNode(edge.target);
      if (!p0 || !dirSn || dirSn.x == null) continue;
      const sx = p0.x;
      const sy = p0.y;
      const tx = dirSn.x;
      const ty = dirSn.y;
      const midX = (sx + tx) / 2;
      const midY = (sy + ty) / 2 - 24;
      darkMatterGfx.lineStyle(1, nebulaColor, 0.1);
      darkMatterGfx.moveTo(sx, sy);
      darkMatterGfx.quadraticCurveTo(midX, midY, tx, ty);
    }
    darkMatterGfx.lineStyle(0);
  }

  function drawEntanglementOverlay() {
    if (!app || !model || !entanglementGfx) return;
    entanglementGfx.clear();
    if (viewLevel !== 'galaxy') return;
    if (!simNodes.length) return;

    const entangledEdges = model.raw.links.filter(l => l.type === 'ENTANGLED').slice(0, MAX_ENTANGLED_DRAW);
    if (!entangledEdges.length) return;

    const time = performance.now() / 1000;
    const pulse = 0.3 + 0.3 * Math.sin(time * 3);
    const entangleColor = 0xf59e0b;

    for (const edge of entangledEdges) {
      const sourceDir = findSimDirForGraphNode(edge.source);
      const targetDir = findSimDirForGraphNode(edge.target);
      if (!sourceDir || !targetDir) continue;
      if (sourceDir === targetDir) continue;
      const sx = sourceDir.x;
      const sy = sourceDir.y;
      const tx = targetDir.x;
      const ty = targetDir.y;
      const midX = (sx + tx) / 2;
      const midY = (sy + ty) / 2 - 30;
      entanglementGfx.lineStyle(2, entangleColor, pulse * 0.4);
      entanglementGfx.moveTo(sx, sy);
      entanglementGfx.quadraticCurveTo(midX, midY, tx, ty);
      entanglementGfx.lineStyle(0);
      const dotRadius = 3 + pulse * 3;
      entanglementGfx.beginFill(entangleColor, pulse * 0.6);
      entanglementGfx.drawCircle(sx, sy, dotRadius);
      entanglementGfx.drawCircle(tx, ty, dotRadius);
      entanglementGfx.endFill();
    }
  }

  function syncPixiFromSim() {
    if (viewLevel !== 'galaxy') {
      for (let i = 0; i < nodePool.length; i++) {
        const p = nodePool[i];
        if (!p || !p.container) continue;
        p.container.visible = false;
        p.container.eventMode = 'none';
        p.simNode = null;
        if (p.label) p.label.visible = false;
      }
      if (galaxyEdgeGfx) {
        galaxyEdgeGfx.clear();
        galaxyEdgeGfx.visible = false;
      }
      return;
    }

    simNodes.forEach((sn, i) => {
      const p = acquireNodePool(i);
      p.simNode = sn;
      p.container.visible = true;
      p.container.eventMode = 'static';
      p.container.x = sn.x;
      p.container.y = sn.y;
      p.container.alpha = searchQuery && !nodeMatchesSearch(sn) ? 0.25 : 1;
      const rVis = sn.radius || 12;
      const hitMult = 1.35;
      p.container.hitArea = new PIXI.Circle(0, 0, rVis * hitMult);
      const sh = p.shape;
      const kind = sn.kind;
      if (kind === 'directory') {
        sh.tint = sn.color;
        sh.scale.set((sn.radius || HEX_BASE_RADIUS) / HEX_BASE_RADIUS);
        sh.alpha = 1.0;
        redrawNodeGlow(p, sn, hoveredSimNode === sn);
      } else if (kind === 'file') {
        drawCircleNode(sh, sn.radius || 14, sn.color, 1, sn.color);
        redrawNodeGlow(p, sn, hoveredSimNode === sn);
      } else if (kind === 'class') {
        drawClassSquare(sh, sn.radius || 12, sn.color);
        redrawNodeGlow(p, sn, hoveredSimNode === sn);
      } else {
        drawDiamond(sh, sn.radius || 10, sn.color);
        redrawNodeGlow(p, sn, hoveredSimNode === sn);
      }

      const lab = p.label;
      if (lab) {
        if (kind === 'directory' && hoveredSimNode === sn) {
          const focal =
            sn.label != null
              ? String(sn.label)
              : sn.name != null
                ? String(sn.name)
                : String(sn.dirId || '');
          lab.text = truncateGraphLabel(focal, 28);
          lab.visible = true;
          lab.position.set(0, (sn.radius || HEX_BASE_RADIUS) + 4);
        } else {
          lab.visible = false;
        }
      }
    });
    for (let j = simNodes.length; j < nodePool.length; j++) {
      nodePool[j].container.visible = false;
      nodePool[j].simNode = null;
      if (nodePool[j].label) nodePool[j].label.visible = false;
    }

    galaxyEdgeFrameCounter++;
    if (galaxyEdgeFrameCounter % 3 === 0) {
      drawGalaxyPhysarumEdges(performance.now() / 1000);
    }
  }

  /** True if pointer is within `screenThresholdPx` (screen space) of any file orbit dot for this directory. */
  function isPointerNearGalaxyDirFileOrbits(dirNode, worldMouse, scale, screenThresholdPx) {
    if (!dirNode || !model) return false;
    const wScale = dirNode._warpScale || 1;
    if (wScale <= 1.5) return false;
    const files = model.dirFilesMap[dirNode.dirId] || [];
    const topFiles = files.slice(0, 30);
    if (!topFiles.length) return false;
    const baseR2 = dirNode.radius || 18;
    const orbitRadius = wScale * baseR2 * 3;
    const cx = dirNode.x;
    const cy = dirNode.y;
    const n = topFiles.length;
    for (let i = 0; i < n; i++) {
      const angle = (i / n) * Math.PI * 2;
      const fx = cx + Math.cos(angle) * orbitRadius;
      const fy = cy + Math.sin(angle) * orbitRadius;
      const dx = worldMouse.x - fx;
      const dy = worldMouse.y - fy;
      const screenDist = Math.sqrt(dx * dx + dy * dy) * scale;
      if (screenDist < screenThresholdPx) return true;
    }
    return false;
  }

  // Gravitational hover + batched child file orbit (galaxy only). Neighbor push deferred — TODO: WebGPU version.
  function updateGalaxyGravitationalHover() {
    if (!_gravScreenPt) _gravScreenPt = new PIXI.Point();
    const hideOrbitLabels = () => {
      visibleChildFiles.length = 0;
      if (stickyTimeout) {
        clearTimeout(stickyTimeout);
        stickyTimeout = null;
      }
      stickyDir = null;
      if (!childrenGfx) return;
      childrenGfx.clear();
      for (let i = 0; i < galaxyLabelPool.length; i++) {
        const lt = galaxyLabelPool[i];
        if (lt) {
          lt.visible = false;
          lt.alpha = 0;
        }
      }
    };

    if (viewLevel !== 'galaxy') {
      hideOrbitLabels();
      if (app && app.view) app.view.style.cursor = 'default';
      return;
    }

    if (!entranceDone || !world || !childrenGfx || !app || !model) {
      hideOrbitLabels();
      if (app && app.view) app.view.style.cursor = 'default';
      return;
    }
    if (!simNodes.length) {
      hideOrbitLabels();
      if (app && app.view) app.view.style.cursor = 'default';
      return;
    }

    visibleChildFiles.length = 0;

    const pointer = app.renderer.events && app.renderer.events.pointer;
    const pg = pointer && pointer.global;
    let worldMouse;
    if (pg) {
      worldMouse = world.toLocal(pg);
    } else {
      worldMouse = { x: 0, y: 0 };
    }

    const scale = world.scale.x;
    const sw = app.screen.width;
    const sh = app.screen.height;
    const margin = 280;

    let rawClosest = null;
    let rawDist = Infinity;

    for (let si = 0; si < simNodes.length; si++) {
      const simNode = simNodes[si];
      if (simNode.kind !== 'directory' || simNode.dirId == null) continue;
      world.toGlobal({ x: simNode.x, y: simNode.y }, _gravScreenPt);
      const gx = _gravScreenPt.x;
      const gy = _gravScreenPt.y;
      if (gx < -margin || gx > sw + margin || gy < -margin || gy > sh + margin) continue;

      const dx = worldMouse.x - simNode.x;
      const dy = worldMouse.y - simNode.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const screenDist = dist * scale;
      const pickR = galaxyDirectoryHoverScreenRadius(simNode, scale);
      if (screenDist < pickR && screenDist < rawDist) {
        rawDist = screenDist;
        rawClosest = simNode;
      }
    }

    let closestNode = rawClosest;
    let closestDist = rawDist;
    let nearChildFile = false;

    if (!pg) {
      closestNode = null;
      closestDist = Infinity;
      if (stickyTimeout) {
        clearTimeout(stickyTimeout);
        stickyTimeout = null;
      }
      stickyDir = null;
    } else {
      if (stickyDir) {
        nearChildFile = isPointerNearGalaxyDirFileOrbits(stickyDir, worldMouse, scale, 40);
      }

      if (rawClosest && rawDist < galaxyDirectoryHoverScreenRadius(rawClosest, scale)) {
        stickyDir = rawClosest;
        if (stickyTimeout) {
          clearTimeout(stickyTimeout);
          stickyTimeout = null;
        }
      } else if (nearChildFile && stickyDir) {
        closestNode = stickyDir;
        closestDist = 100;
        if (stickyTimeout) {
          clearTimeout(stickyTimeout);
          stickyTimeout = null;
        }
      } else if (stickyDir) {
        if (!stickyTimeout) {
          stickyTimeout = setTimeout(() => {
            stickyDir = null;
            stickyTimeout = null;
          }, STICKY_DELAY);
        }
        closestNode = stickyDir;
        closestDist = 140;
      }
    }

    for (let si = 0; si < simNodes.length; si++) {
      const sn = simNodes[si];
      if (sn.kind !== 'directory') continue;
      sn._warpScale = sn._warpScale || 1;
      if (sn === closestNode && closestNode) {
        const hoverR = galaxyDirectoryHoverScreenRadius(closestNode, scale);
        const proximity = 1 - closestDist / hoverR;
        const massScale = Math.min((closestNode.childCount || 10) / 50, 1.5);
        const targetScale = Math.min(
          1 + proximity * proximity * 1.5 * massScale,
          GALAXY_MAX_WARP_SCALE
        );
        sn._warpScale += (targetScale - sn._warpScale) * 0.12;
      } else {
        sn._warpScale += (1.0 - sn._warpScale) * 0.12;
      }
    }

    for (let i = 0; i < simNodes.length; i++) {
      const sn = simNodes[i];
      const p = nodePool[i];
      if (!p || !p.container.visible || p.simNode !== sn) continue;
      if (sn.kind === 'directory') {
        p.container.scale.set(sn._warpScale || 1);
      }
    }

    childrenGfx.clear();

    const cn = closestNode;
    const wScale = cn ? (cn._warpScale || 1) : 1;

    if (cn && wScale > 1.3) {
      const baseR = cn.radius || 18;
      const orbitRadius = wScale * baseR * 3;
      const ringAlpha = Math.min(0.08, (wScale - 1.3) * 0.1);
      const ringRadius = orbitRadius * 1.5;
      const rc = cn.color || COLORS.directory;
      childrenGfx.lineStyle(1, rc, ringAlpha);
      childrenGfx.drawCircle(cn.x, cn.y, ringRadius);
      childrenGfx.lineStyle(1, rc, ringAlpha * 0.6);
      childrenGfx.drawCircle(cn.x, cn.y, ringRadius * 1.3);
      childrenGfx.lineStyle(1, rc, ringAlpha * 0.3);
      childrenGfx.drawCircle(cn.x, cn.y, ringRadius * 1.6);
      childrenGfx.lineStyle(0);
    }

    const showFiles = !!(cn && pg && wScale > 1.5 && closestDist <= 140);
    let topFiles = [];
    let childAlpha = 0;
    let orbitRadius = 0;

    if (showFiles) {
      const files = model.dirFilesMap[cn.dirId] || [];
      topFiles = files.slice(0, 30);
      const baseR2 = cn.radius || 18;
      orbitRadius = wScale * baseR2 * 3;
      childAlpha = Math.max(0, Math.min(1, (wScale - 1.5) / 1.5));

      if (topFiles.length) {
        const cx = cn.x;
        const cy = cn.y;
        const n = topFiles.length;
        for (let i = 0; i < n; i++) {
          const angle = (i / n) * Math.PI * 2;
          const fx = cx + Math.cos(angle) * orbitRadius;
          const fy = cy + Math.sin(angle) * orbitRadius;
          const fileRadius = 8 + Math.min(topFiles[i].symbolCount / 5, 12);
          const lang = extLang(topFiles[i].name);
          const color =
            lang === 'py' ? COLORS.filePython : lang === 'ts' ? COLORS.fileTS : COLORS.fileMixed;
          const fp = resolveDirFilePath(cn.dirId, topFiles[i].name);
          const dx = worldMouse.x - fx;
          const dy = worldMouse.y - fy;
          const distToFile = Math.sqrt(dx * dx + dy * dy) * scale;
          const isHovered = distToFile < 30;
          const drawRadius = isHovered ? fileRadius * 1.4 : fileRadius;
          const drawAlpha = isHovered ? Math.min(1, childAlpha * 1.5) : childAlpha;
          visibleChildFiles.push({
            x: fx,
            y: fy,
            radius: fileRadius,
            name: topFiles[i].name,
            symbolCount: topFiles[i].symbolCount,
            dirId: cn.dirId,
            fileId: topFiles[i].id,
            filePath: fp,
          });
          childrenGfx.beginFill(color, 0.2 * drawAlpha);
          childrenGfx.drawCircle(fx, fy, drawRadius * (isHovered ? 3 : 2.5));
          childrenGfx.endFill();
          childrenGfx.beginFill(color, 0.85 * drawAlpha);
          childrenGfx.drawCircle(fx, fy, drawRadius);
          childrenGfx.endFill();
          if (isHovered) {
            childrenGfx.lineStyle(2, 0xffffff, 0.8 * drawAlpha);
          } else if (topFiles[i].symbolCount >= 50) {
            childrenGfx.lineStyle(2, 0xffffff, 0.5 * childAlpha);
          } else {
            childrenGfx.lineStyle(1, 0xffffff, 0.3 * childAlpha);
          }
          childrenGfx.drawCircle(fx, fy, drawRadius);
          childrenGfx.lineStyle(0);
        }
      }
    }

    for (let i = 0; i < GALAXY_LABEL_POOL_SIZE; i++) {
      const lt = galaxyLabelPool[i];
      if (!lt) continue;
      if (showFiles && topFiles.length && i < topFiles.length && childAlpha > 0.1) {
        const n = topFiles.length;
        const angle = (i / n) * Math.PI * 2;
        const fx = cn.x + Math.cos(angle) * orbitRadius;
        const fy = cn.y + Math.sin(angle) * orbitRadius;
        const fileRadius = 8 + Math.min(topFiles[i].symbolCount / 5, 12);
        const nm = topFiles[i].name;
        const sc = topFiles[i].symbolCount;
        const ldx = worldMouse.x - fx;
        const ldy = worldMouse.y - fy;
        const labelDist = Math.sqrt(ldx * ldx + ldy * ldy) * scale;
        const labelHovered = labelDist < 30;
        lt.text =
          (nm.length > 16 ? nm.slice(0, 14) + '…' : nm) + ' (' + sc + ')';
        lt.position.set(fx, fy + fileRadius + 4);
        lt.alpha = labelHovered ? 1.0 : childAlpha;
        lt.visible = true;
        lt.style.fontSize = 12;
      } else {
        lt.visible = false;
        lt.alpha = 0;
      }
    }

    if (app && app.view) {
      app.view.style.cursor = pg && nearChildFile ? 'pointer' : 'default';
    }
  }

  function galaxyLinkFluxAndEndpoints(l) {
    const maxNW = model && model.maxNodeWeight > 0 ? model.maxNodeWeight : 1;
    const maxEW = model && model.maxEdgeWeight > 0 ? model.maxEdgeWeight : 1;
    const sid = typeof l.source === 'object' && l.source !== null ? l.source.id : l.source;
    const tid = typeof l.target === 'object' && l.target !== null ? l.target.id : l.target;
    const s =
      typeof l.source === 'object' && l.source !== null && l.source.x != null
        ? l.source
        : simNodes.find(n => n.id === sid);
    const t =
      typeof l.target === 'object' && l.target !== null && l.target.x != null
        ? l.target
        : simNodes.find(n => n.id === tid);
    if (!s || !t) return { flux: 0, s: null, t: null, sid, tid, lt: l.type || 'CALLS' };
    const cS = s.totalEdgeWeight || 0;
    const cT = t.totalEdgeWeight || 0;
    let flux = (cS + cT) / (2 * maxNW);
    if (!Number.isFinite(flux) || maxNW <= 0) {
      flux = Math.min((l.weight || 1) / maxEW, 1);
    }
    flux = Math.min(1, Math.max(0, flux));
    return { flux, s, t, sid, tid, lt: l.type || 'CALLS' };
  }

  function rebuildMyceliumFlowPool() {
    for (let i = 0; i < MYCELIUM_POOL_SIZE; i++) myceliumParticlePool[i].active = false;
    if (!model || viewLevel !== 'galaxy' || !simNodes.length || !simLinks.length) return;

    const ranked = [];
    for (let e = 0; e < simLinks.length; e++) {
      const l = simLinks[e];
      const { flux } = galaxyLinkFluxAndEndpoints(l);
      ranked.push({ e, flux });
    }
    ranked.sort((a, b) => b.flux - a.flux);
    const top = ranked.slice(0, MYCELIUM_TOP_EDGES);

    let pi = 0;
    for (let ri = 0; ri < top.length; ri++) {
      const { e, flux } = top[ri];
      if (pi >= MYCELIUM_POOL_SIZE) break;
      let want = Math.floor(flux * 8) + 1;
      want = Math.min(want, 9, MYCELIUM_POOL_SIZE - pi);
      const l = simLinks[e];
      const lt = l.type || 'CALLS';
      for (let k = 0; k < want && pi < MYCELIUM_POOL_SIZE; k++) {
        const p = myceliumParticlePool[pi];
        p.edgeIndex = e;
        p.t = Math.random();
        p.speed = lerp(0.001, 0.008, flux) * (0.85 + Math.random() * 0.3);
        p.size = lerp(1.0, 2.5, flux);
        p.alpha = lerp(0.3, 0.9, flux);
        p.reverse = lt === 'IMPORTS' && k % 2 === 1;
        p.active = true;
        pi++;
      }
    }
  }

  function findGalaxyClosestDirUnderPointer() {
    if (!_gravScreenPt) _gravScreenPt = new PIXI.Point();
    if (!entranceDone || viewLevel !== 'galaxy' || !world || !app || !simNodes.length) return null;
    const pointer = app.renderer.events && app.renderer.events.pointer;
    const pg = pointer && pointer.global;
    if (!pg) return null;
    const worldMouse = world.toLocal(pg);
    const scale = world.scale.x;
    const sw = app.screen.width;
    const sh = app.screen.height;
    const margin = 280;
    let closestNode = null;
    let closestDist = Infinity;
    for (let si = 0; si < simNodes.length; si++) {
      const simNode = simNodes[si];
      if (simNode.kind !== 'directory' || simNode.dirId == null) continue;
      world.toGlobal({ x: simNode.x, y: simNode.y }, _gravScreenPt);
      const gx = _gravScreenPt.x;
      const gy = _gravScreenPt.y;
      if (gx < -margin || gx > sw + margin || gy < -margin || gy > sh + margin) continue;
      const dx = worldMouse.x - simNode.x;
      const dy = worldMouse.y - simNode.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const screenDist = dist * scale;
      const pickR = galaxyDirectoryHoverScreenRadius(simNode, scale);
      if (screenDist < pickR && screenDist < closestDist) {
        closestDist = screenDist;
        closestNode = simNode;
      }
    }
    return closestNode;
  }

  function galaxyFlowBoostNodeIdSet() {
    const set = new Set();
    if (hoveredSimNode && hoveredSimNode.id != null) set.add(hoveredSimNode.id);
    const cn = findGalaxyClosestDirUnderPointer();
    if (cn && cn.id != null) set.add(cn.id);
    return set;
  }

  function quadBezierPoint(sx, sy, cx, cy, tx, ty, u) {
    const omu = 1 - u;
    const x = omu * omu * sx + 2 * omu * u * cx + u * u * tx;
    const y = omu * omu * sy + 2 * omu * u * cy + u * u * ty;
    return { x, y };
  }

  function physarumOrganicControl(sx, sy, tx, ty, edgeIndex, timeSec) {
    const mx = (sx + tx) / 2;
    const my = (sy + ty) / 2;
    const perpX = -(ty - sy);
    const perpY = tx - sx;
    const len = Math.sqrt(perpX * perpX + perpY * perpY) || 1;
    const noiseOffset = (Math.sin(edgeIndex * 0.7 + timeSec * 0.3) * 15) / len;
    const cx = mx + perpX * noiseOffset;
    const cy = my + perpY * noiseOffset;
    return { cx, cy };
  }

  function endpointOnScreenForContainer(container, lx, ly, marginPx) {
    if (!_physarumScreenPt) _physarumScreenPt = new PIXI.Point();
    _physarumScreenPt.set(lx, ly);
    container.toGlobal(_physarumScreenPt, _physarumScreenPt);
    const sw = app.screen.width;
    const sh = app.screen.height;
    return (
      _physarumScreenPt.x >= -marginPx &&
      _physarumScreenPt.x <= sw + marginPx &&
      _physarumScreenPt.y >= -marginPx &&
      _physarumScreenPt.y <= sh + marginPx
    );
  }

  function physarumEdgeColorByType(linkType, flux) {
    const lt = linkType || 'CALLS';
    if (lt === 'DARK_FORCE' || lt === 'DARK') return 0xf59e0b;
    if (lt === 'IMPORTS') return COLORS.edgeImports;
    if (lt === 'INHERITS') return COLORS.edgeInherits;
    if (lt === 'ENTANGLED') return 0xf59e0b;
    if (lt === 'DECORATES') return COLORS.edgeDecorates;
    if (lt === 'DEFINES') return COLORS.edgeDefines;
    return lerpColor(0x22d3ee, 0xffffff, flux);
  }

  function drawPhysarumDashedQuadratic(gfx, sx, sy, cx, cy, tx, ty, width, color, alpha) {
    const steps = 20;
    let prev = quadBezierPoint(sx, sy, cx, cy, tx, ty, 0);
    const dash = 6;
    const gap = 5;
    let drawn = true;
    let inDash = 0;
    for (let i = 1; i <= steps; i++) {
      const u = i / steps;
      const pt = quadBezierPoint(sx, sy, cx, cy, tx, ty, u);
      const seg = Math.hypot(pt.x - prev.x, pt.y - prev.y);
      let t0 = 0;
      while (t0 < seg - 1e-6) {
        const cap = drawn ? dash : gap;
        const need = cap - inDash;
        const step = Math.min(need, seg - t0);
        const f1 = t0 / seg;
        const f2 = (t0 + step) / seg;
        const ax = prev.x + (pt.x - prev.x) * f1;
        const ay = prev.y + (pt.y - prev.y) * f1;
        const bx = prev.x + (pt.x - prev.x) * f2;
        const by = prev.y + (pt.y - prev.y) * f2;
        if (drawn) {
          gfx.lineStyle(width, color, alpha);
          gfx.moveTo(ax, ay);
          gfx.lineTo(bx, by);
        }
        t0 += step;
        inDash += step;
        if (inDash >= cap - 1e-6) {
          drawn = !drawn;
          inDash = 0;
        }
      }
      prev = pt;
    }
  }

  /** Straight dashed segment (cheaper than quadratic bezier sampling). */
  function drawPhysarumDashedLine(gfx, sx, sy, tx, ty, width, color, alpha) {
    const len = Math.hypot(tx - sx, ty - sy);
    if (len < 1e-6) return;
    const dash = 6;
    const gap = 5;
    let u = 0;
    let drawn = true;
    while (u < len - 1e-6) {
      const cap = drawn ? dash : gap;
      const u2 = Math.min(u + cap, len);
      if (drawn) {
        gfx.lineStyle(width, color, alpha);
        const ax = sx + ((tx - sx) * u) / len;
        const ay = sy + ((ty - sy) * u) / len;
        const bx = sx + ((tx - sx) * u2) / len;
        const by = sy + ((ty - sy) * u2) / len;
        gfx.moveTo(ax, ay);
        gfx.lineTo(bx, by);
      }
      u = u2;
      drawn = !drawn;
    }
  }

  function drawGalaxyPhysarumEdges(timeSec) {
    if (!galaxyEdgeGfx || !world || !app) return;
    galaxyEdgeGfx.clear();
    galaxyEdgeGfx.visible = true;
    const margin = 120;
    const maxNW = model && model.maxNodeWeight > 0 ? model.maxNodeWeight : 1;
    const maxEW = model && model.maxEdgeWeight > 0 ? model.maxEdgeWeight : 1;

    const staging = [];

    for (let e = 0; e < simLinks.length; e++) {
      const l = simLinks[e];
      const sid = typeof l.source === 'object' && l.source !== null ? l.source.id : l.source;
      const tid = typeof l.target === 'object' && l.target !== null ? l.target.id : l.target;
      const s = typeof l.source === 'object' && l.source !== null && l.source.x != null
        ? l.source
        : simNodes.find(n => n.id === sid);
      const t = typeof l.target === 'object' && l.target !== null && l.target.x != null
        ? l.target
        : simNodes.find(n => n.id === tid);
      if (!s || !t || s.x == null || t.x == null) continue;

      const vs = endpointOnScreenForContainer(world, s.x, s.y, margin);
      const vt = endpointOnScreenForContainer(world, t.x, t.y, margin);
      if (!vs || !vt) continue;

      const cS = s.totalEdgeWeight || 0;
      const cT = t.totalEdgeWeight || 0;
      let flux = (cS + cT) / (2 * maxNW);
      if (!Number.isFinite(flux) || maxNW <= 0) {
        flux = Math.min((l.weight || 1) / maxEW, 1);
      }
      flux = Math.min(1, Math.max(0, flux));

      const pulse = GPU_SAFE_MODE ? 1 : 1.0 + Math.sin(timeSec * 0.8 + e * 0.5) * 0.15;
      const thickness = 1;
      let alpha;
      if (GPU_SAFE_MODE) {
        alpha = 0.3;
      } else {
        const baseAlpha = lerp(0.08, 0.9, flux);
        alpha = baseAlpha * (0.85 + pulse * 0.15);
      }

      const lt = l.type || 'CALLS';
      const edgeKey = sid < tid ? sid + '\0' + tid : tid + '\0' + sid;
      const pulseUntil = traceEdgePulseUntil.get(edgeKey);
      if (pulseUntil != null && performance.now() < pulseUntil) {
        alpha = Math.min(1, alpha * 1.55);
      }

      const col = physarumEdgeColorByType(lt, flux);
      if (lt === 'DARK_FORCE' || lt === 'DARK') {
        alpha *= 0.55;
      }

      const wBucket = Math.round(thickness * 4);
      const aBucket = Math.round(alpha * 40);

      staging.push({
        sx: s.x,
        sy: s.y,
        tx: t.x,
        ty: t.y,
        width: 1,
        col,
        alpha,
        wBucket,
        aBucket,
        lt,
        flux,
      });
    }

    staging.sort((a, b) => b.flux - a.flux);
    const capped = staging.slice(0, MAX_GALAXY_PHYSARUM_EDGES_PER_FRAME);
    const solid = [];
    const dashed = [];
    for (let si = 0; si < capped.length; si++) {
      const ed = capped[si];
      if (ed.lt === 'DARK_FORCE' || ed.lt === 'DARK') {
        dashed.push(ed);
      } else {
        solid.push(ed);
      }
    }

    solid.sort((a, b) => {
      if (a.col !== b.col) return a.col - b.col;
      if (a.wBucket !== b.wBucket) return a.wBucket - b.wBucket;
      return a.aBucket - b.aBucket;
    });

    let lastKey = '';
    for (const ed of solid) {
      const key = ed.col + ':' + ed.wBucket + ':' + ed.aBucket;
      if (key !== lastKey) {
        galaxyEdgeGfx.lineStyle(1, ed.col, ed.alpha);
        lastKey = key;
      }
      galaxyEdgeGfx.moveTo(ed.sx, ed.sy);
      galaxyEdgeGfx.lineTo(ed.tx, ed.ty);
    }

    for (const ed of dashed) {
      drawPhysarumDashedLine(galaxyEdgeGfx, ed.sx, ed.sy, ed.tx, ed.ty, 1, ed.col, ed.alpha);
    }

    galaxyEdgeGfx.lineStyle(0);

    const now = performance.now();
    const expiredKeys = [];
    for (const [k, until] of traceEdgePulseUntil) {
      if (until < now) expiredKeys.push(k);
    }
    for (let i = 0; i < expiredKeys.length; i++) {
      traceEdgePulseUntil.delete(expiredKeys[i]);
    }
  }

  function drawSubviewPhysarumEdges(edgeGfx, coordContainer, edges, timeSec) {
    if (!edgeGfx) return;
    edgeGfx.clear();
    if (!coordContainer || !edges || !edges.length) {
      edgeGfx.lineStyle(0);
      return;
    }
    const margin = 100;
    const deg = new Map();
    for (const edge of edges) {
      const s = edge.source;
      const t = edge.target;
      if (!s || !t) continue;
      deg.set(s, (deg.get(s) || 0) + 1);
      deg.set(t, (deg.get(t) || 0) + 1);
    }
    let maxD = 1;
    for (const v of deg.values()) maxD = Math.max(maxD, v);

    const solid = [];
    const dashed = [];

    for (let ei = 0; ei < edges.length; ei++) {
      const edge = edges[ei];
      const s = edge.source;
      const t = edge.target;
      if (!s || !t || s.x == null || t.x == null) continue;

      const vs = endpointOnScreenForContainer(coordContainer, s.x, s.y, margin);
      const vt = endpointOnScreenForContainer(coordContainer, t.x, t.y, margin);
      if (!vs && !vt) continue;

      const dS = deg.get(s) || 1;
      const dT = deg.get(t) || 1;
      let flux = (dS + dT) / (2 * maxD);
      flux = Math.min(1, Math.max(0, flux));

      const pulse = GPU_SAFE_MODE ? 1 : 1.0 + Math.sin(timeSec * 0.8 + ei * 0.5) * 0.15;
      const thickness = 1;
      let useAlpha;
      if (GPU_SAFE_MODE) {
        useAlpha = 0.3;
      } else {
        const baseAlpha = lerp(0.08, 0.9, flux);
        useAlpha = baseAlpha * (0.85 + pulse * 0.15);
      }
      const lt = edge.type || 'CALLS';
      const col = physarumEdgeColorByType(lt, flux);
      if (lt === 'DARK_FORCE' || lt === 'DARK') {
        useAlpha *= 0.55;
      }
      const wBucket = Math.round(thickness * 4);
      const aBucket = Math.round(useAlpha * 40);
      const entry = {
        sx: s.x,
        sy: s.y,
        tx: t.x,
        ty: t.y,
        width: 1,
        col,
        alpha: useAlpha,
        wBucket,
        aBucket,
        lt,
      };
      if (lt === 'DARK_FORCE' || lt === 'DARK') {
        dashed.push(entry);
      } else {
        solid.push(entry);
      }
    }

    solid.sort((a, b) => {
      if (a.col !== b.col) return a.col - b.col;
      if (a.wBucket !== b.wBucket) return a.wBucket - b.wBucket;
      return a.aBucket - b.aBucket;
    });

    let lastKey = '';
    for (const ed of solid) {
      const key = ed.col + ':' + ed.wBucket + ':' + ed.aBucket;
      if (key !== lastKey) {
        edgeGfx.lineStyle(1, ed.col, ed.alpha);
        lastKey = key;
      }
      edgeGfx.moveTo(ed.sx, ed.sy);
      edgeGfx.lineTo(ed.tx, ed.ty);
    }

    for (const ed of dashed) {
      drawPhysarumDashedLine(edgeGfx, ed.sx, ed.sy, ed.tx, ed.ty, 1, ed.col, ed.alpha);
    }

    edgeGfx.lineStyle(0);
  }

  function tickAndRenderStarView() {
    if (viewLevel !== 'star' || !world) return;
    const sc = world.children.find(c => c._omnixType === 'star');
    if (!sc || !sc._edges || !sc._edgeGfx || !sc._nodes) return;
    if (sc._growthPhaseComplete && sc._sim && sc._sim.alpha() > 0.002) sc._sim.tick();

    const time = performance.now() / 1000;
    const nodes = sc._nodes;
    const edges = sc._edges;
    const edgeGfx = sc._edgeGfx;
    const growthGfx = sc._growthGfx;
    const signalGfx = sc._signalGfx;
    const particles = sc._signalParticles;

    if (!sc._growthPhaseComplete && growthGfx) {
      drawStarGrowthEdges(growthGfx, sc);
      edgeGfx.clear();
      edgeGfx.lineStyle(0);
    } else {
      drawSubviewPhysarumEdges(edgeGfx, sc, edges, time);
      if (growthGfx) {
        growthGfx.clear();
        growthGfx.lineStyle(0);
      }
    }

    signalGfx.clear();
    if (!sc._growthPhaseComplete) {
      return;
    }
    for (const p of particles) {
      p.progress += p.speed;
      if (p.progress > 1) p.progress = 0;
      const edge = p.edge;
      if (!edge) continue;
      const s = edge.source;
      const t = edge.target;
      if (!s || !t) continue;
      const ei = edges.indexOf(edge);
      let pos;
      let tpos;
      const tp = Math.max(0, p.progress - 0.06);
      if (GPU_SAFE_MODE) {
        pos = {
          x: s.x + (t.x - s.x) * p.progress,
          y: s.y + (t.y - s.y) * p.progress,
        };
        tpos = {
          x: s.x + (t.x - s.x) * tp,
          y: s.y + (t.y - s.y) * tp,
        };
        signalGfx.beginFill(p.color, 0.65);
        signalGfx.drawRect(Math.floor(pos.x), Math.floor(pos.y), 1, 1);
        signalGfx.endFill();
        signalGfx.beginFill(p.color, 0.2);
        signalGfx.drawRect(Math.floor(tpos.x), Math.floor(tpos.y), 1, 1);
        signalGfx.endFill();
      } else {
        const { cx, cy } = physarumOrganicControl(s.x, s.y, t.x, t.y, ei >= 0 ? ei : 0, time);
        pos = quadBezierPoint(s.x, s.y, cx, cy, t.x, t.y, p.progress);
        tpos = quadBezierPoint(s.x, s.y, cx, cy, t.x, t.y, tp);
        signalGfx.beginFill(p.color, 0.7);
        signalGfx.drawRect(pos.x - 1, pos.y - 1, 2, 2);
        signalGfx.endFill();
        signalGfx.beginFill(p.color, 0.25);
        signalGfx.drawRect(tpos.x - 1, tpos.y - 1, 2, 2);
        signalGfx.endFill();
      }
    }

    for (const node of nodes) {
      if (node._heartbeatPhase == null) node._heartbeatPhase = Math.random() * Math.PI * 2;
      const beat = 1 + 0.04 * Math.sin(time * 1.5 + node._heartbeatPhase);
      node.glow.scale.set(beat);
      const baseA = 0.5 + 0.3 * Math.sin(time * 1.5 + node._heartbeatPhase);
      node.glow.alpha = node._hover ? Math.min(1, baseA * 1.35) : baseA;
    }
  }

  function tickAndRenderPlanetView() {
    if (viewLevel !== 'planet' || !world) return;
    const pc = world.children.find(c => c._omnixType === 'planet');
    if (!pc || !pc._edges || !pc._edgeGfx || !pc._nodes) return;
    if (pc._sim && pc._sim.alpha() > 0.002) pc._sim.tick();

    const pcx = pc._planetCenterX != null ? pc._planetCenterX : app.screen.width / 2;
    const pcy = pc._planetCenterY != null ? pc._planetCenterY : app.screen.height / 2;
    const pbr = pc._planetBoundaryR;
    const nodes = pc._nodes;
    if (pbr > 0 && nodes && nodes.length) {
      for (let ni = 0; ni < nodes.length; ni++) {
        const pn = nodes[ni];
        const dx = pn.x - pcx;
        const dy = pn.y - pcy;
        const d = Math.hypot(dx, dy);
        if (d > pbr) {
          const f = pbr / d;
          pn.x = pcx + dx * f;
          pn.y = pcy + dy * f;
        }
      }
      for (let nj = 0; nj < nodes.length; nj++) {
        const pn2 = nodes[nj];
        if (pn2.container) pn2.container.position.set(pn2.x, pn2.y);
      }
    }

    const time = performance.now() / 1000;
    const edges = pc._edges;
    const edgeGfx = pc._edgeGfx;
    const signalGfx = pc._signalGfx;
    const particles = pc._signalParticles;

    drawSubviewPhysarumEdges(edgeGfx, pc, edges, time);

    signalGfx.clear();
    for (const p of particles) {
      p.progress += p.speed;
      if (p.progress > 1) p.progress = 0;
      const edge = p.edge;
      if (!edge) continue;
      const s = edge.source;
      const t = edge.target;
      if (!s || !t) continue;
      const ei = edges.indexOf(edge);
      let pos;
      let tpos;
      const tp = Math.max(0, p.progress - 0.06);
      if (GPU_SAFE_MODE) {
        pos = {
          x: s.x + (t.x - s.x) * p.progress,
          y: s.y + (t.y - s.y) * p.progress,
        };
        tpos = {
          x: s.x + (t.x - s.x) * tp,
          y: s.y + (t.y - s.y) * tp,
        };
        signalGfx.beginFill(p.color, 0.65);
        signalGfx.drawRect(Math.floor(pos.x), Math.floor(pos.y), 1, 1);
        signalGfx.endFill();
        signalGfx.beginFill(p.color, 0.2);
        signalGfx.drawRect(Math.floor(tpos.x), Math.floor(tpos.y), 1, 1);
        signalGfx.endFill();
      } else {
        const { cx, cy } = physarumOrganicControl(s.x, s.y, t.x, t.y, ei >= 0 ? ei : 0, time);
        pos = quadBezierPoint(s.x, s.y, cx, cy, t.x, t.y, p.progress);
        tpos = quadBezierPoint(s.x, s.y, cx, cy, t.x, t.y, tp);
        signalGfx.beginFill(p.color, 0.7);
        signalGfx.drawRect(pos.x - 1, pos.y - 1, 2, 2);
        signalGfx.endFill();
        signalGfx.beginFill(p.color, 0.25);
        signalGfx.drawRect(tpos.x - 1, tpos.y - 1, 2, 2);
        signalGfx.endFill();
      }
    }

    for (const node of nodes) {
      if (node._heartbeatPhase == null) node._heartbeatPhase = Math.random() * Math.PI * 2;
      const beat = 1 + 0.04 * Math.sin(time * 1.5 + node._heartbeatPhase);
      node.glow.scale.set(beat);
      const baseA = 0.5 + 0.3 * Math.sin(time * 1.5 + node._heartbeatPhase);
      node.glow.alpha = node._hover ? Math.min(1, baseA * 1.35) : baseA;

      const mem = node.membraneGfx;
      const cls = node.classification;
      if (mem && cls) {
        const wobble = 1 + Math.sin(time * 1.2 + node.index * 0.7) * 0.03;
        const r = node.radius * wobble;
        mem.clear();
        mem.lineStyle(1.5, cls.color, 0.7);
        mem.drawCircle(0, 0, r);
      }
    }
  }

  function drawSignalFlow() {
    if (!signalFlowGfx) return;
    signalFlowGfx.clear();
    if (viewLevel !== 'galaxy') return;
    if (!entranceDone || !simNodes.length || !simLinks.length) return;

    const timeSec = performance.now() / 1000;
    const boostIds = galaxyFlowBoostNodeIdSet();
    const nL = simLinks.length;
    const edgeMeta = new Array(nL);
    for (let e = 0; e < nL; e++) {
      edgeMeta[e] = galaxyLinkFluxAndEndpoints(simLinks[e]);
    }

    for (let pi = 0; pi < MYCELIUM_POOL_SIZE; pi++) {
      const p = myceliumParticlePool[pi];
      if (!p.active) continue;

      const ei = p.edgeIndex;
      if (ei < 0 || ei >= nL) {
        p.active = false;
        continue;
      }

      const { flux, s, t, sid, tid, lt } = edgeMeta[ei];
      if (!s || !t || s.x == null || t.x == null) {
        p.active = false;
        continue;
      }

      const isDarkEdge = lt === 'DARK_FORCE' || lt === 'DARK';

      const edgeBoost =
        boostIds.size > 0 && (boostIds.has(sid) || boostIds.has(tid));
      const spdMul = edgeBoost ? 2 : 1;
      const alphaMul = edgeBoost ? 1.5 : 1;

      const sp = p.speed * spdMul;
      p.t += sp;
      while (p.t >= 1) p.t -= 1;

      if (isDarkEdge && !darkMatterVisible) continue;

      const u = p.reverse ? 1 - p.t : p.t;
      const pos = {
        x: s.x + (t.x - s.x) * u,
        y: s.y + (t.y - s.y) * u,
      };
      const col = physarumEdgeColorByType(lt, flux);
      if (GPU_SAFE_MODE) {
        const baseA = Math.min(1, p.alpha * alphaMul * 0.95);
        signalFlowGfx.beginFill(col, baseA);
        signalFlowGfx.drawRect(Math.floor(pos.x), Math.floor(pos.y), 1, 1);
        signalFlowGfx.endFill();
      } else {
        const pulse = 0.7 + Math.sin(timeSec * 3 + p.t * Math.PI * 2) * 0.3;
        const baseA = Math.min(1, p.alpha * alphaMul);
        const coreA = Math.min(1, baseA * pulse);
        signalFlowGfx.beginFill(col, coreA);
        signalFlowGfx.drawRect(pos.x - 1, pos.y - 1, 2, 2);
        signalFlowGfx.endFill();
      }
    }
  }

  function findGalaxyGravClosestForRipple() {
    if (!_gravScreenPt) _gravScreenPt = new PIXI.Point();
    if (!entranceDone || viewLevel !== 'galaxy' || !world || !app || !simNodes.length) return null;

    const pointer = app.renderer.events && app.renderer.events.pointer;
    const pg = pointer && pointer.global;
    if (!pg) return null;

    const worldMouse = world.toLocal(pg);
    const scale = world.scale.x;
    const sw = app.screen.width;
    const sh = app.screen.height;
    const margin = 280;

    let closestNode = null;
    let closestDist = Infinity;

    for (let si = 0; si < simNodes.length; si++) {
      const simNode = simNodes[si];
      if (simNode.kind !== 'directory' || simNode.dirId == null) continue;
      world.toGlobal({ x: simNode.x, y: simNode.y }, _gravScreenPt);
      const gx = _gravScreenPt.x;
      const gy = _gravScreenPt.y;
      if (gx < -margin || gx > sw + margin || gy < -margin || gy > sh + margin) continue;

      const dx = worldMouse.x - simNode.x;
      const dy = worldMouse.y - simNode.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const screenDist = dist * scale;
      const pickR = galaxyDirectoryHoverScreenRadius(simNode, scale);
      if (screenDist < pickR && screenDist < closestDist) {
        closestDist = screenDist;
        closestNode = simNode;
      }
    }
    return closestNode;
  }

  function drawRippleImpact() {
    if (!rippleGfx) return;
    rippleGfx.clear();
    if (viewLevel !== 'galaxy') return;
    if (!entranceDone) return;

    const cn = findGalaxyGravClosestForRipple();
    if (!cn || (cn._warpScale || 1) < 1.3) return;

    const time = performance.now() / 1000;
    const cx = cn.x;
    const cy = cn.y;
    const nowMs = performance.now();

    const nbrIds = new Set();
    const cid = cn.id;
    currentLinks.forEach(l => {
      const s = typeof l.source === 'object' && l.source !== null ? l.source.id : l.source;
      const t = typeof l.target === 'object' && l.target !== null ? l.target.id : l.target;
      if (s === cid) nbrIds.add(t);
      if (t === cid) nbrIds.add(s);
    });

    for (let ring = 0; ring < 3; ring++) {
      const phase = (time * 0.8 + ring * 0.33) % 1;
      const radius = 20 + phase * 200;
      const alpha = (1 - phase) * 0.12;
      rippleGfx.lineStyle(1.5, 0x6366f1, alpha);
      rippleGfx.drawCircle(cx, cy, radius);

      for (let ni = 0; ni < simNodes.length; ni++) {
        const sn = simNodes[ni];
        if (!nbrIds.has(sn.id) || sn === cn) continue;
        const d = Math.hypot(sn.x - cx, sn.y - cy);
        if (Math.abs(radius - d) < 14) {
          sn._rippleFlashUntil = nowMs + 100;
        }
      }
    }
    rippleGfx.lineStyle(0);
  }

  function applyDirectoryHeartbeatAndGlow() {
    if (viewLevel !== 'galaxy') return;
    if (!entranceDone || !simNodes.length) return;
    const time = performance.now() / 1000;
    const nowMs = performance.now();

    for (let i = 0; i < simNodes.length; i++) {
      const sn = simNodes[i];
      if (sn.kind !== 'directory') continue;
      const pool = nodePool[i];
      if (!pool || !pool.container.visible || pool.simNode !== sn) continue;

      const warp = sn._warpScale || 1;
      const timeMul =
        timelineVisible && timelineData && sn._timelineScale !== undefined ? sn._timelineScale : 1;
      const beat = 1 + 0.03 * Math.sin(time * sn._heartbeatSpeed * Math.PI * 2 + sn._heartbeatPhase);
      pool.container.scale.set(warp * timeMul * beat);

      const isHover = hoveredSimNode === sn;
      const flash = sn._rippleFlashUntil && nowMs < sn._rippleFlashUntil ? 1.25 : 1;
      const glowRhythm = 1 + 0.12 * Math.sin(time * sn._heartbeatSpeed * Math.PI * 2 + sn._heartbeatPhase);
      const pulse = (isHover ? 1.05 : 1) * (0.94 + 0.06 * glowRhythm) * flash;
      const base = pool.glow._glowBaseAlpha != null ? pool.glow._glowBaseAlpha : 1;
      pool.glow.alpha = base * pulse;
    }
  }

  function nodeMatchesSearch(sn) {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const raw = sn.raw;
    const name = (sn.name || '').toLowerCase();
    const id = (sn.id || '').toLowerCase();
    const file = (sn.file || '').toLowerCase();
    const dir = (sn.dirId || '').toLowerCase();
    if (name.includes(q) || id.includes(q) || file.includes(q) || dir.includes(q)) return true;
    if (raw) {
      if ((raw.name || '').toLowerCase().includes(q)) return true;
      if ((raw.id || '').toLowerCase().includes(q)) return true;
    }
    return false;
  }

  function findMatchingDir(snapDirs, dirId) {
    if (snapDirs == null) return null;
    const candidates = [dirId];
    if (dirId === '') candidates.push('.');
    if (dirId === '.') candidates.push('');
    for (let c = 0; c < candidates.length; c++) {
      const k = candidates[c];
      if (k != null && snapDirs[k]) return snapDirs[k];
    }
    for (const [key, val] of Object.entries(snapDirs)) {
      if (dirId.endsWith(key) || key.endsWith(dirId) ||
          dirId.includes(key) || key.includes(dirId)) {
        return val;
      }
    }
    return null;
  }

  function applyTimelineSnapshot(idx) {
    if (!timelineData || !timelineData.snapshots || !timelineData.snapshots.length) return;
    const snap = timelineData.snapshots[idx];
    if (!snap) return;

    document.getElementById('timeline-date').textContent = snap.date;
    document.getElementById('timeline-info').textContent =
      snap.author + ': "' + snap.message + '"';
    document.getElementById('timeline-stats').textContent =
      snap.total_files + ' files · ' + Number(snap.total_lines).toLocaleString() + ' lines';

    for (let i = 0; i < simNodes.length; i++) {
      const simNode = simNodes[i];
      if (simNode.kind !== 'directory') {
        delete simNode._timelineScale;
        delete simNode._timelineAlpha;
        continue;
      }
      const dirPath = simNode.dirId != null ? simNode.dirId : '';
      const snapDir = findMatchingDir(snap.directories, dirPath);

      if (snapDir) {
        simNode._timelineScale = Math.max(0.3, Math.min(2.5, snapDir.lines / 500));
        simNode._timelineAlpha = 1.0;
      } else {
        simNode._timelineScale = 0.1;
        simNode._timelineAlpha = 0.15;
      }
    }
  }

  function applyTimelineToPixiContainers() {
    if (!timelineVisible || !timelineData || viewLevel !== 'galaxy') return;
    for (let i = 0; i < simNodes.length; i++) {
      const simNode = simNodes[i];
      if (simNode.kind !== 'directory') continue;
      const pool = nodePool[i];
      if (!pool || !pool.container || !pool.container.visible || pool.simNode !== simNode) continue;
      if (simNode._timelineScale === undefined) continue;
      const baseScale = simNode._warpScale || 1;
      const timeScale = simNode._timelineScale || 1;
      pool.container.scale.set(baseScale * timeScale);
      const searchDim = searchQuery && !nodeMatchesSearch(simNode) ? 0.25 : 1;
      const ta = simNode._timelineAlpha != null ? simNode._timelineAlpha : 1;
      pool.container.alpha = searchDim * ta;
    }
  }

  function loadLevelGalaxy() {
    hideSymbolPopup();
    notifyScopeVisualEmpty(null);
    cleanupStarView();
    cleanupPlanetView();
    resetGalaxyDrillState();
    viewLevel = 'galaxy';
    selectedDir = null;
    selectedFile = null;
    currentNodes = model.galaxy.nodes;
    currentLinks = model.galaxy.links;
    world.alpha = 1;
    killTweens();
    if (world) {
      gsap.killTweensOf(world);
      gsap.killTweensOf(world.scale);
    }
    if (starGraphics) gsap.killTweensOf(starGraphics);
    if (galaxyEdgeGfx) gsap.killTweensOf(galaxyEdgeGfx);
    startSimulation(currentNodes, currentLinks);
    restoreGalaxyView();
    notifyViewerScope({ kind: 'repo' });
    gsap.fromTo(world, { alpha: 0.3 }, { alpha: 1, duration: 0.45, ease: 'power2.out' });
    if (timelineVisible && timelineData) {
      const s = document.getElementById('timeline-slider');
      applyTimelineSnapshot(parseInt(s.value, 10) || 0);
    }
  }

  function zoomOutOne() {
    goBack();
  }

  studio._applyScopeNavigation = function (spec) {
    if (!model || !app) return;
    const normPath = p => String(p || '').replace(/\\/g, '/');
    if (!spec || spec.kind === 'repo') {
      loadLevelGalaxy();
      return;
    }
    if (spec.kind === 'directory') {
      const p = normPath(spec.path);
      if (!p) {
        loadLevelGalaxy();
        return;
      }
      /**
       * slice17c1 — React GraphCanvas applies navigationSpec whenever currentScope changes.
       * createStarView already set viewLevel === 'star' and notifyViewerScope(directory).
       * Without this guard, loadLevelGalaxy() runs and wipes the drill (R7 regression).
       */
      if (
        (viewLevel === 'star' || viewLevel === 'galaxy') &&
        selectedDir != null &&
        normPath(selectedDir) === p
      ) {
        return;
      }
      if (viewLevel !== 'galaxy') {
        loadLevelGalaxy();
      }
      transitionToStar(p, null);
      return;
    }
    if (spec.kind === 'file') {
      const fp = normPath(spec.path);
      const dir = dirname(fp);
      if (!fp || !dir) {
        loadLevelGalaxy();
        return;
      }
      if (viewLevel === 'planet' && selectedFile) {
        const curFp = normPath(
          selectedFile.filePath || resolveDirFilePath(selectedDir, selectedFile.name)
        );
        if (curFp === fp) {
          return;
        }
      }
      loadLevelGalaxy();
      transitionToStar(dir, null);
      const delaySec = STAR_DRILL_CREATE_DELAY_SEC + 0.35;
      gsap.delayedCall(delaySec, () => {
        if (!model) return;
        const files = model.dirFilesMap[dir] || [];
        const base = basename(fp);
        let hit = files.find(f => f.name === base);
        if (!hit) {
          hit = files.find(f => resolveDirFilePath(dir, f.name) === fp);
        }
        if (!hit || viewLevel !== 'star') return;
        const fd = Object.assign({}, hit, {
          dirId: dir,
          filePath: resolveDirFilePath(dir, hit.name),
        });
        transitionToPlanet(fd);
      });
    }
  };

  studio._canGoBack = function () {
    return viewLevel === 'star' || viewLevel === 'planet';
  };

  studio._goBack = function () {
    if (viewLevel === 'star' || viewLevel === 'planet') goBack();
  };

  function relayoutOmnixViews() {
    if (!app || !world || !model) return;
    const cx = app.screen.width / 2;
    const cy = app.screen.height / 2;
    if (viewLevel === 'star' && selectedDir && starNodes.length) {
      if (starViewTitle) starViewTitle.position.set(cx, cy);
      const sc = world.children.find(c => c._omnixType === 'star');
      if (sc && sc._sim && sc._growthPhaseComplete) {
        sc._sim.force('center', d3.forceCenter(cx, cy));
        sc._sim.force('x', d3.forceX(cx).strength(0.05));
        sc._sim.force('y', d3.forceY(cy).strength(0.05));
        sc._sim.alpha(0.28).restart();
      }
    } else if (viewLevel === 'planet' && selectedFile && planetNodes.length && selectedDir) {
      if (planetViewTitle) planetViewTitle.position.set(cx, cy);
      const pc = world.children.find(c => c._omnixType === 'planet');
      if (pc) {
        pc._planetCenterX = cx;
        pc._planetCenterY = cy;
        pc._planetBoundaryR = Math.min(app.screen.width, app.screen.height) * 0.36;
        if (pc._sim) {
          pc._sim.force('center', d3.forceCenter(cx, cy));
          pc._sim.force('x', d3.forceX(cx).strength(0.06));
          pc._sim.force('y', d3.forceY(cy).strength(0.06));
          pc._sim.alpha(0.28).restart();
        }
      }
    }
  }

  function updateBreadcrumb() {
    const canGoBack = viewLevel === 'star' || viewLevel === 'planet';
    if (studio._options && typeof studio._options.onNavigationStateChange === 'function') {
      try { studio._options.onNavigationStateChange(canGoBack); } catch (_e) { /* */ }
    }
    const bc = document.getElementById('breadcrumb');
    if (!bc) return;
    bc.innerHTML = '';
    const addCrumb = (label, level, data) => {
      const span = document.createElement('span');
      span.className = 'crumb' + (level === 'current' ? ' current' : '');
      span.textContent = label;
      span.dataset.level = data || '';
      if (level !== 'current') {
        span.addEventListener('click', () => {
          if (data === 'galaxy') {
            loadLevelGalaxy();
          } else if (data === 'star' && selectedDir) {
            if (viewLevel === 'planet') {
              cleanupPlanetView();
              viewLevel = 'star';
              selectedFile = null;
              restoreStarView();
            }
          }
        });
      }
      bc.appendChild(span);
    };

    addCrumb('OMNIX', viewLevel === 'galaxy' ? 'current' : '', 'galaxy');

    if ((viewLevel === 'star' || viewLevel === 'planet') && selectedDir) {
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '›';
      bc.appendChild(sep);
      const dirTitle = basename(selectedDir) || selectedDir;
      const label = dirTitle.length > 40 ? dirTitle.slice(0, 37) + '…' : dirTitle;
      addCrumb(label, viewLevel === 'star' ? 'current' : '', 'star');
    }

    if (viewLevel === 'planet' && selectedFile) {
      const sep2 = document.createElement('span');
      sep2.className = 'sep';
      sep2.textContent = '›';
      bc.appendChild(sep2);
      const fn = selectedFile.name || basename(selectedFile.filePath || '') || '?';
      const flabel = fn.length > 40 ? fn.slice(0, 37) + '…' : fn;
      addCrumb(flabel, 'current', 'file');
    }

    gsap.fromTo(bc, { opacity: 0.5 }, { opacity: 1, duration: 0.35 });
  }

  function drawBackground() {
    const w = app.screen.width;
    const h = app.screen.height;
    bgGraphics.clear();
    const steps = 12;
    for (let i = 0; i < steps; i++) {
      const t = i / (steps - 1);
      const c = lerpColor(COLORS.bg, COLORS.bgGradientEnd, t);
      bgGraphics.beginFill(c, 1);
      bgGraphics.drawRect(0, (h / steps) * i, w, h / steps + 1);
      bgGraphics.endFill();
    }
  }

  let starfieldTwinkle = null;
  function buildStarfield() {
    if (starfieldTwinkle) {
      starfieldTwinkle.kill();
      starfieldTwinkle = null;
    }
    starGraphics.clear();
    const n = 200;
    for (let i = 0; i < n; i++) {
      const x = Math.random() * app.screen.width;
      const y = Math.random() * app.screen.height;
      const s = 0.4 + Math.random() * 1.2;
      starGraphics.beginFill(0xffffff, 0.15 + Math.random() * 0.35);
      starGraphics.drawCircle(x, y, s);
      starGraphics.endFill();
    }
    starGraphics.alpha = 0.85;
    starfieldTwinkle = gsap.to(starGraphics, {
      alpha: 1,
      duration: 2.4,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
    });
  }

  function drawHexGrid() {
    gridGraphics.clear();
    const h = 40;
    const w = app.screen.width;
    const ht = app.screen.height;
    gridGraphics.lineStyle(1, 0x6366f1, 0.06);
    for (let y = -h; y < ht + h; y += h * 0.866) {
      let row = 0;
      for (let x = -w; x < w + w; x += h * 1.5) {
        const ox = (row % 2) * h * 0.75;
        const cx = x + ox;
        const pts = [];
        for (let i = 0; i < 6; i++) {
          const a = (Math.PI / 3) * i - Math.PI / 6;
          pts.push(cx + Math.cos(a) * h * 0.45, y + Math.sin(a) * h * 0.45);
        }
        gridGraphics.moveTo(pts[0], pts[1]);
        for (let k = 2; k < pts.length; k += 2) gridGraphics.lineTo(pts[k], pts[k + 1]);
        gridGraphics.closePath();
        row++;
      }
    }
  }

  function initPixi() {
    const host = studio._container;
    const omnixPixiBootOptions = {
      width: window.innerWidth,
      height: window.innerHeight,
      backgroundColor: COLORS.bg,
      antialias: false,
      resolution: 1,
      autoDensity: true,
      powerPreference: 'low-power',
      preserveDrawingBuffer: false,
    };
    /* slice18a-lite: Pixi v7 @pixi/app Application constructor calls autoDetectRenderer(omnixPixiBootOptions); WebGPU preference requires Pixi v8+ (do not migrate here). */
    app = new PIXI.Application(omnixPixiBootOptions);
    host.appendChild(app.view);
    const _omnixGlCanvas = app.view;
    if (_omnixGlCanvas && _omnixGlCanvas.addEventListener) {
      _omnixGlCanvas.addEventListener('webglcontextlost', (e) => {
        e.preventDefault();
        console.warn('WebGL context lost — attempting recovery');
      });
      _omnixGlCanvas.addEventListener('webglcontextrestored', () => {
        console.log('WebGL context restored');
      });
    }

    const hexBlueprint = new PIXI.Graphics();
    drawHexagon(hexBlueprint, HEX_BASE_RADIUS, 0xffffff, 0.25, 2, 0xffffff);
    galaxyDirectoryHexTexture = app.renderer.generateTexture(hexBlueprint, { resolution: 4 });
    hexBlueprint.destroy();
    console.debug('[slice18a-lite.1] hex texture built', {
      width: galaxyDirectoryHexTexture.width,
      height: galaxyDirectoryHexTexture.height,
    });

    const glowBlueprint = new PIXI.Graphics();
    for (let ri = GLOW_TEXTURE_RING_COUNT; ri > 0; ri--) {
      const r = (ri / GLOW_TEXTURE_RING_COUNT) * GLOW_TEXTURE_BASE_RADIUS;
      const ringA = ((GLOW_TEXTURE_RING_COUNT - ri + 1) / GLOW_TEXTURE_RING_COUNT) * 0.2;
      glowBlueprint.beginFill(0xffffff, ringA);
      glowBlueprint.drawCircle(0, 0, r);
      glowBlueprint.endFill();
    }
    galaxyDirectoryGlowTexture = app.renderer.generateTexture(glowBlueprint, { resolution: 2 });
    glowBlueprint.destroy();
    console.debug('[slice18a-lite.1] glow texture built', {
      width: galaxyDirectoryGlowTexture.width,
      height: galaxyDirectoryGlowTexture.height,
    });

    bgGraphics = new PIXI.Graphics();
    starGraphics = new PIXI.Graphics();
    gridGraphics = new PIXI.Graphics();
    world = new PIXI.Container();
    darkMatterGfx = new PIXI.Graphics();
    darkMatterGfx.eventMode = 'none';
    layerEdges = new PIXI.Container();
    galaxyEdgeGfx = new PIXI.Graphics();
    galaxyEdgeGfx.eventMode = 'none';
    layerEdges.addChild(galaxyEdgeGfx);
    entanglementGfx = new PIXI.Graphics();
    entanglementGfx.eventMode = 'none';
    layerNodes = new PIXI.Container();
    signalFlowGfx = new PIXI.Graphics();
    signalFlowGfx.eventMode = 'none';
    childrenGfx = new PIXI.Graphics();
    childrenGfx.eventMode = 'none';
    rippleGfx = new PIXI.Graphics();
    rippleGfx.eventMode = 'none';
    window._aiTraceGfx = new PIXI.Graphics();
    window._aiTraceGfx.eventMode = 'none';
    world.addChild(darkMatterGfx);
    world.addChild(layerEdges);
    world.addChild(signalFlowGfx);
    world.addChild(entanglementGfx);
    world.addChild(childrenGfx);
    world.addChild(rippleGfx);
    world.addChild(window._aiTraceGfx);
    world.addChild(layerNodes);
    layerEdges.eventMode = 'none';

    app.stage.addChild(bgGraphics);
    app.stage.addChild(starGraphics);
    app.stage.addChild(gridGraphics);
    app.stage.addChild(world);

    galaxyLabelPool = [];
    for (let i = 0; i < GALAXY_LABEL_POOL_SIZE; i++) {
      const t = new PIXI.Text('', {
        fontFamily: 'Outfit, sans-serif',
        fontSize: 12,
        fill: 0xe2e8f0,
        align: 'center',
      });
      t.anchor.set(0.5, 0);
      t.visible = false;
      t.alpha = 0;
      t.eventMode = 'none';
      world.addChild(t);
      galaxyLabelPool.push(t);
    }

    app.stage.eventMode = 'static';
    app.stage.hitArea = app.screen;
    app.stage.on('pointerdown', onStageDown);
    app.stage.on('pointermove', onStageMove);
    app.stage.on('pointerup', onStageUp);
    app.stage.on('pointerupoutside', onStageUp);
    app.view.addEventListener('wheel', onWheel, { passive: false });
    app.view.addEventListener('contextmenu', ev => ev.preventDefault());
    app.view.addEventListener('mousemove', ev => {
      if (!hoveredSimNode) return;
      const t = document.getElementById('tooltip');
      if (t.style.display !== 'block') return;
      showTooltip(hoveredSimNode, ev.clientX, ev.clientY);
    });

    drawBackground();
    drawHexGrid();
    buildStarfield();

    world.position.set(0, 0);
    world.scale.set(1);
    worldScale = 1;
    worldTx = 0;
    worldTy = 0;
    targetWorldScale = 1;
    targetWorldTx = 0;
    targetWorldTy = 0;

    let lastFps = performance.now();
    let frames = 0;
    const _omnixMainTicker = () => {
      frames++;
      const now = performance.now();
      if (now - lastFps >= 500) {
        const fps = Math.round((frames * 1000) / (now - lastFps));
        setOmnixFpsSample(fps);
        frames = 0;
        lastFps = now;
      }
      if (viewLevel === 'galaxy') {
        if (simulation && simulation.alpha() > 0.002) {
          simulation.tick();
        }
        syncPixiFromSim();
      } else if (viewLevel === 'star') {
        tickAndRenderStarView();
      } else if (viewLevel === 'planet') {
        tickAndRenderPlanetView();
      }
      updateGalaxyGravitationalHover();
      applyTimelineToPixiContainers();
      applyDirectoryHeartbeatAndGlow();
      drawSignalFlow();
      drawRippleImpact();
      drawEntanglementOverlay();
      drawDarkMatterOverlay();
      if (aiTraceActive && viewLevel === 'galaxy' && window._aiTraceGfx) {
        const gfx = window._aiTraceGfx;
        gfx.clear();
        const targetSimNode = simNodes.find(sn => {
          if (sn.kind !== 'directory') return false;
          const id = sn.dirId || (sn.raw && sn.raw.id) || '';
          return id === aiTraceTarget || (aiTraceTarget && aiTraceTarget.startsWith(id + '/'));
        });
        if (targetSimNode && targetSimNode.x != null) {
          const time = performance.now() / 1000;
          for (let ring = 0; ring < 4; ring++) {
            const phase = (time * 0.6 + ring * 0.25) % 1;
            const radius = 20 + phase * 300;
            const alpha = (1 - phase) * 0.15;
            gfx.lineStyle(2, 0xa855f7, alpha);
            gfx.drawCircle(targetSimNode.x, targetSimNode.y, radius);
          }
          gfx.lineStyle(0);
          const pulse = 0.5 + 0.5 * Math.sin(time * 4);
          gfx.beginFill(0xa855f7, pulse * 0.4);
          gfx.drawCircle(targetSimNode.x, targetSimNode.y, 8);
          gfx.endFill();
        }
      }
    };
    app.ticker.add(_omnixMainTicker);
    studio._mainTicker = _omnixMainTicker;
  }

  let dragStart = null;
  let worldStart = null;
  let didDrag = false;

  function isStageBackgroundTarget(t) {
    return (
      t === app.stage ||
      t === world ||
      t === layerEdges ||
      t === layerNodes ||
      t === gridGraphics ||
      t === bgGraphics ||
      t === starGraphics ||
      t === darkMatterGfx ||
      t === signalFlowGfx ||
      t === entanglementGfx ||
      t === childrenGfx ||
      t === rippleGfx ||
      t === window._aiTraceGfx
    );
  }

  function onStageDown(e) {
    if (pointerEventButton(e) === 2) return;
    if (isStageBackgroundTarget(e.target)) {
      dragStart = { x: e.global.x, y: e.global.y };
      worldStart = { x: world.position.x, y: world.position.y };
      didDrag = false;
    }
  }

  function onStageMove(e) {
    if (!dragStart) return;
    const dx = e.global.x - dragStart.x;
    const dy = e.global.y - dragStart.y;
    if (Math.hypot(dx, dy) > 4) didDrag = true;
    world.position.set(worldStart.x + dx, worldStart.y + dy);
    worldTx = world.position.x;
    worldTy = world.position.y;
    targetWorldTx = worldTx;
    targetWorldTy = worldTy;
  }

  function onStageUp(e) {
    const btn = pointerEventButton(e);
    if (btn === 2) {
      if (isStageBackgroundTarget(e.target)) {
        if (viewLevel !== 'galaxy') goBack();
        else if (xrayOpen) closeXray();
      }
      dragStart = null;
      return;
    }
    if (dragStart && !didDrag) {
      if (isStageBackgroundTarget(e.target)) {
        if (xrayOpen) closeXray();
      }
    }
    dragStart = null;
  }

  function onWheel(ev) {
    ev.preventDefault();
    const delta = ev.deltaY > 0 ? 0.92 : 1.08;
    const ns = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, world.scale.x * delta));
    const rect = app.view.getBoundingClientRect();
    const lx = ev.clientX - rect.left;
    const ly = ev.clientY - rect.top;
    const wx = (lx - world.position.x) / world.scale.x;
    const wy = (ly - world.position.y) / world.scale.y;
    world.scale.set(ns);
    world.position.set(lx - wx * ns, ly - wy * ns);
    worldScale = ns;
    targetWorldScale = ns;
    worldTx = world.position.x;
    worldTy = world.position.y;
    targetWorldTx = worldTx;
    targetWorldTy = worldTy;
  }

  function resizePixi() {
    if (!app) return;
    app.renderer.resize(window.innerWidth, window.innerHeight);
    app.stage.hitArea = app.screen;
    drawBackground();
    drawHexGrid();
    buildStarfield();
    if (viewLevel === 'galaxy' && simNodes.length) {
      fitWorldToNodes(false);
      syncPixiFromSim();
    }
    relayoutOmnixViews();
  }

  /** --- Search --- */
  function runSearchIndex() {
    if (!model) return;
    const q = searchQuery.toLowerCase();
    searchMatches = [];
    if (!q) {
      document.getElementById('search-count').textContent = '';
      document.getElementById('search-hint').style.display = 'none';
      syncPixiFromSim();
      return;
    }
    model.raw.nodes.forEach(n => {
      const hay = ((n.name || '') + (n.id || '') + (n.file || '')).toLowerCase();
      if (hay.includes(q)) searchMatches.push(n);
    });
    document.getElementById('search-count').textContent = searchMatches.length ? searchMatches.length + ' hits' : '0 hits';
    const hint = document.getElementById('search-hint');
    if (searchMatches.length) {
      const m = searchMatches[0];
      const bn = m.name || m.id;
      const fp = m.file || '';
      hint.textContent = bn + (fp ? ' → ' + fp : '');
      hint.style.display = 'block';
    } else {
      hint.style.display = 'none';
    }
    syncPixiFromSim();
  }

  function zoomToRawNode(n) {
    if (!n || !n.file || !model) return;
    const dir = dirname(n.file);
    const fp = n.file;
    const baseName = basename(fp);
    const mapList = model.dirFilesMap[dir] || [];
    const fileEntry = mapList.find(f => f.name === baseName);
    const fileData = Object.assign({}, fileEntry || { name: baseName, symbolCount: 0 }, {
      dirId: dir,
      filePath: fp,
    });

    if (n.type === 'file') {
      if (viewLevel !== 'galaxy') loadLevelGalaxy();
      const dirNode = simNodes.find(sn => sn.kind === 'directory' && sn.dirId === dir);
      gsap.delayedCall(0.05, () => transitionToStar(dir, dirNode || null));
      gsap.delayedCall(1.45, () => {
        if (selectedDir === dir && viewLevel === 'star') transitionToPlanet(fileData);
      });
      return;
    }
    if (n.type === 'function' || n.type === 'class' || n.type === 'method') {
      if (viewLevel !== 'galaxy') loadLevelGalaxy();
      const dirNode = simNodes.find(sn => sn.kind === 'directory' && sn.dirId === dir);
      gsap.delayedCall(0.05, () => transitionToStar(dir, dirNode || null));
      gsap.delayedCall(1.45, () => {
        if (selectedDir === dir && viewLevel === 'star') transitionToPlanet(fileData);
      });
      gsap.delayedCall(2.0, () => {
        const syms = getSymbolsForFile(fp, dir);
        const hit = syms.find(s => s.name === n.name && s.type === n.type);
        if (hit) {
          if (
            (hit.type === 'function' || hit.type === 'class' || hit.type === 'method') &&
            typeof studio._options.onFunctionNodeClick === 'function' &&
            hit &&
            hit.id
          ) {
            try {
              studio._options.onFunctionNodeClick(String(hit.id));
            } catch (_e) { /* */ }
          } else {
            showSymbolDetailPopup(hit, fileData);
          }
        }
      });
      return;
    }
    if (dir) {
      if (viewLevel !== 'galaxy') loadLevelGalaxy();
      const dirNode = simNodes.find(sn => sn.kind === 'directory' && sn.dirId === dir);
      gsap.delayedCall(0.05, () => transitionToStar(dir, dirNode || null));
    }
  }

  /** --- Entrance --- */
  let entranceDone = false;
  function skipEntrance() {
    if (entranceDone) return;
    entranceDone = true;
    gsap.killTweensOf('#entrance *');
    const el = document.getElementById('entrance');
    gsap.to(el, {
      opacity: 0,
      duration: 0.35,
      onComplete: () => {
        el.style.display = 'none';
        document.getElementById('ui-fade').classList.add('visible');
      },
    });
    try { localStorage.setItem(STORAGE_VISITED, '1'); } catch (e) { /* ignore */ }
  }

  function playEntrance(stats) {
    const skip = localStorage.getItem(STORAGE_VISITED) === '1';
    if (skip) {
      entranceDone = true;
      document.getElementById('entrance').style.display = 'none';
      document.getElementById('ui-fade').classList.add('visible');
      return;
    }
    const tl = gsap.timeline({
      onComplete: () => {
        skipEntrance();
      },
    });
    tl.to('#ent-title', { opacity: 1, duration: 0.5, ease: 'power2.out' }, 0);
    tl.to('#ent-sub', {
      opacity: 1,
      duration: 0.4,
      onStart: () => {
        document.getElementById('ent-sub').textContent =
          'Scanning ' + (stats.files || 0) + ' files…';
      },
    }, 0.5);
    tl.add(() => {
      buildStarfield();
      starGraphics.alpha = 0;
      gsap.to(starGraphics, { alpha: 1, duration: 0.5 });
    }, 1);
    tl.add(() => {
      if (model && simNodes.length) {
        // Thousands of staggered scale tweens exhaust WebGL / leave orphaned GSAP targets
        // after context loss; cap the fan-out for large galaxy graphs.
        const ENTRANCE_STAGGER_NODE_CAP = 200;
        const heavy = simNodes.length > ENTRANCE_STAGGER_NODE_CAP;
        nodePool.forEach((p, i) => {
          if (i >= simNodes.length) return;
          p.container.visible = true;
          p.simNode = simNodes[i];
          p.container.x = simNodes[i].x;
          p.container.y = simNodes[i].y;
          gsap.killTweensOf(p.container.scale);
          if (heavy) {
            p.container.scale.set(1, 1);
          } else {
            gsap.fromTo(p.container.scale, { x: 0, y: 0 }, {
              x: 1,
              y: 1,
              duration: 0.45,
              ease: 'back.out(1.4)',
              delay: i * 0.03,
            });
          }
        });
      }
    }, 1.5);
    tl.add(() => {
      if (galaxyEdgeGfx) {
        galaxyEdgeGfx.alpha = 0;
        gsap.to(galaxyEdgeGfx, { alpha: 1, duration: 0.45, ease: 'sine.out' });
      }
    }, 2.5);
    tl.add(() => {
      const files = stats.files || 0;
      const funcs = (stats.functions || 0) + (stats.methods || 0);
      const edges = stats.edges || 0;
      document.getElementById('ent-sub').textContent = files + ' files · ' + funcs + ' functions · ' + edges + ' edges';
      gsap.fromTo('#ent-sub', { opacity: 0.4 }, { opacity: 1, duration: 0.4 });
    }, 3);
    tl.to('#ent-title', { opacity: 0, duration: 0.4 }, 3.5);
    tl.to('#ent-sub', { opacity: 0, duration: 0.4 }, 3.5);
  }

  function showLoadError(msg) {
    const wrap = document.getElementById('loading-error');
    document.getElementById('loading-error-msg').innerHTML = escapeHtml(msg);
    wrap.classList.add('visible');
  }

  function updateStatsPanel(stats) {
    document.getElementById('stat-files').textContent = stats.files ?? 0;
    document.getElementById('stat-functions').textContent = (stats.functions ?? 0) + (stats.methods ?? 0);
    document.getElementById('stat-classes').textContent = stats.classes ?? 0;
    document.getElementById('stat-edges').textContent = stats.edges ?? 0;
    document.getElementById('stat-dark').textContent = stats.dark_matter ?? 0;
    document.getElementById('stat-entangled').textContent = stats.entangled ?? 0;
  }
  /** --- Boot (Studio) --- */
  function __omnixWireOptionalDom() {
    const g = (id) => document.getElementById(id);
    const el = (id) => g(id);
    if (el('entrance')) el('entrance').addEventListener('click', skipEntrance);
    if (el('btn-fullscreen')) {
      el('btn-fullscreen').addEventListener('click', () => {
        if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
        else document.exitFullscreen?.();
      });
    }
    if (el('btn-dark-matter')) {
      el('btn-dark-matter').addEventListener('click', () => {
        darkMatterVisible = !darkMatterVisible;
        const b = el('btn-dark-matter');
        if (b) {
          b.style.opacity = darkMatterVisible ? '1' : '0.5';
          b.style.borderColor = darkMatterVisible ? '#8b5cf6' : 'rgba(99,102,241,0.2)';
        }
      });
    }
    if (el('btn-timeline')) {
      el('btn-timeline').addEventListener('click', () => {
        timelineVisible = !timelineVisible;
        const pan = el('timeline-panel');
        if (pan) pan.style.display = timelineVisible ? 'block' : 'none';
        const b = el('btn-timeline');
        if (b) {
          b.style.opacity = timelineVisible ? '1' : '0.5';
          b.style.borderColor = timelineVisible ? '#a855f7' : 'rgba(99,102,241,0.2)';
        }
        if (timelineVisible) {
          const s = el('timeline-slider');
          if (s) applyTimelineSnapshot(parseInt(s.value, 10) || 0);
        } else {
          for (let i = 0; i < simNodes.length; i++) {
            delete simNodes[i]._timelineScale;
            delete simNodes[i]._timelineAlpha;
          }
          syncPixiFromSim();
        }
      });
    }
    if (el('timeline-slider')) {
      el('timeline-slider').addEventListener('input', (e) => {
        const idx = parseInt(e.target.value, 10);
        applyTimelineSnapshot(idx);
      });
    }
    if (el('btn-export')) {
      el('btn-export').addEventListener('click', async () => {
        if (!GRAPH_API_URL) {
          alert('Export needs the OMNIX server URL.');
          return;
        }
        try {
          const r = await fetch(GRAPH_API_URL, { cache: 'no-store' });
          if (!r.ok) {
            alert('Export failed: HTTP ' + r.status);
            return;
          }
          const j = await r.json();
          const blob = new Blob([JSON.stringify(j, null, 2)], { type: 'application/json' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'graph.json';
          a.click();
          URL.revokeObjectURL(a.href);
        } catch (e) {
          alert('Export failed');
        }
      });
    }
    if (el('search-input')) {
      el('search-input').addEventListener('input', () => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
          const si = el('search-input');
          searchQuery = (si && si.value && si.value.trim()) || '';
          runSearchIndex();
        }, SEARCH_DEBOUNCE_MS);
      });
      el('search-input').addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && searchMatches.length) zoomToRawNode(searchMatches[0]);
      });
    }
    if (el('xray-close')) el('xray-close').addEventListener('click', closeXray);
  }

  function __omnixKeydownHandler(ev) {
    if (ev.key === 'Enter' && document.activeElement && document.activeElement.id === 'ai-question-input') {
      const dirId = xrayDirId || '';
      void runAIAsk(dirId);
      return;
    }
    if (ev.key === 'Escape') {
      hideSymbolPopup();
      if (xrayOpen) {
        closeXray();
        return;
      }
      if (viewLevel === 'planet' || viewLevel === 'star') {
        goBack();
        return;
      }
      if (viewLevel === 'galaxy' && selectedDir) {
        selectedDir = null;
        killTweens();
        gsap.set(layerEdges, { alpha: 1 });
        nodePool.forEach((p) => {
          if (!p.container) return;
          gsap.killTweensOf(p.container);
          gsap.killTweensOf(p.container.scale);
          p.container.alpha = searchQuery && p.simNode && !nodeMatchesSearch(p.simNode) ? 0.25 : 1;
        });
        syncPixiFromSim();
        updateBreadcrumb();
        if (typeof studio._options.onDeselect === 'function') {
          try {
            studio._options.onDeselect();
          } catch (_e) { /* */ }
        }
        return;
      }
      killTweens();
      resetGalaxyDrillState();
      fitWorldToNodes();
      updateBreadcrumb();
    }
  }

  function __omnixResizeHandler() {
    resizePixi();
  }

  __omnixWireOptionalDom();
  window.addEventListener('keydown', __omnixKeydownHandler);
  window.addEventListener('resize', __omnixResizeHandler);

  studio._loadGraphFromData = function (data) {
    let payload = data;
    if (getActiveGalaxyStressTier() == null) {
      const tier =
        typeof window !== 'undefined' ? detectGalaxyStressTier(window) : null;
      if (tier) {
        activateGalaxyStressTier(tier);
        payload = generateStressGraph(tier);
        // eslint-disable-next-line no-console
        console.debug('[slice18a-lite.1] stress harness active', {
          tier,
          nodes: payload.nodes.length,
          edges: payload.links.length,
        });
      }
    } else if (!payload || payload.fromStress !== true) {
      // eslint-disable-next-line no-console
      console.debug('[slice18a-lite.1] bootstrap_complete suppressed', {
        reason: 'stress harness active',
        tier: getActiveGalaxyStressTier(),
      });
      return;
    }

    if (
      !payload ||
      !Array.isArray(payload.nodes) ||
      !Array.isArray(payload.links)
    ) {
      showLoadError('Invalid graph payload (expected nodes + links arrays).');
      return;
    }
    const sanitized = sanitizePayload(payload);
    if (getActiveGalaxyStressTier()) {
      studio._stressCatalogNodes = sanitized.nodes;
      studio._stressCatalogLinks = sanitized.links;
    } else {
      studio._stressCatalogNodes = undefined;
      studio._stressCatalogLinks = undefined;
    }
    rawGraphData = sanitized;
    model = buildGraphModel(sanitized);
    void ensureAiStatus();
    try {
      updateStatsPanel(sanitized.stats || {});
    } catch (_e) { /* */ }
    const sdd = document.getElementById('stat-dark');
    if (sdd) {
      sdd.textContent = String(sanitized.nodes.filter((n) => n.type === 'dark_matter').length);
    }
    const sde = document.getElementById('stat-entangled');
    if (sde) {
      sde.textContent = String(sanitized.links.filter((l) => l.type === 'ENTANGLED').length);
    }
    if (!app) {
      initPixi();
    }
    loadLevelGalaxy();
    if (TIMELINE_API_URL) {
      fetch(TIMELINE_API_URL, { cache: 'no-store' })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data && data.snapshots && data.snapshots.length > 0) {
            timelineData = data;
            const btn = document.getElementById('btn-timeline');
            if (btn) btn.style.display = '';
            const slider = document.getElementById('timeline-slider');
            if (slider) {
              slider.max = String(data.snapshots.length - 1);
              slider.value = String(data.snapshots.length - 1);
            }
            const td = document.getElementById('timeline-date');
            if (td) td.textContent = data.first_date;
            const te = document.getElementById('timeline-date-end');
            if (te) te.textContent = data.last_date;
          }
        })
        .catch(() => {});
    }
    if (localStorage.getItem(STORAGE_VISITED) === '1') {
      entranceDone = true;
    }
    playEntrance((sanitized && sanitized.stats) || {});
  };

  /** Studio: incremental updates (T2+); T1 is no-op */
  studio._ingestDelta = function (_message) { /* T2 */ };

  studio._destroy = function () {
    window.removeEventListener('keydown', __omnixKeydownHandler);
    window.removeEventListener('resize', __omnixResizeHandler);
    if (starfieldTwinkle) {
      try {
        starfieldTwinkle.kill();
      } catch (_e) { /* */ }
    }
    starfieldTwinkle = null;
    try {
      killTweens();
    } catch (_e) { /* */ }
    try {
      nodePool.forEach(p => {
        if (!p || !p.container) return;
        gsap.killTweensOf(p.container);
        gsap.killTweensOf(p.container.scale);
      });
      if (world) {
        gsap.killTweensOf(world);
        gsap.killTweensOf(world.scale);
      }
      if (starGraphics) gsap.killTweensOf(starGraphics);
      if (galaxyEdgeGfx) gsap.killTweensOf(galaxyEdgeGfx);
      if (layerEdges) gsap.killTweensOf(layerEdges);
    } catch (_e) { /* */ }
    if (world && world.children) {
      for (let wi = 0; wi < world.children.length; wi++) {
        const ch = world.children[wi];
        if (ch._omnixType !== 'planet' || !ch._nodes) continue;
        for (let pi = 0; pi < ch._nodes.length; pi++) {
          const pn = ch._nodes[pi];
          if (!pn || !pn.container) continue;
          if (pn.container._omnixBornTween) {
            try {
              pn.container._omnixBornTween.kill();
            } catch (_e) { /* */ }
            delete pn.container._omnixBornTween;
          }
          gsap.killTweensOf(pn.container);
          gsap.killTweensOf(pn.container.scale);
        }
      }
    }
    if (app) {
      try {
        if (studio._mainTicker) {
          app.ticker.remove(studio._mainTicker);
        }
      } catch (_e) { /* */ }
      try {
        app.destroy(true, { children: true, texture: true });
      } catch (_e) { /* */ }
    }
    app = null;
  };


}
