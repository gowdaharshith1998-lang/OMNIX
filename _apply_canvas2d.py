#!/usr/bin/env python3
"""One-shot canvas2d port transforms on index.html (forward-only edits)."""
from pathlib import Path
import re

p = Path("/home/harsh/omnix/src/web/index.html")
text = p.read_text(encoding="utf-8")

# --- Remove any remaining pixi script lines ---
text = re.sub(
    r'\s*<script[^>]*pixi[^>]*></script>\s*\n',
    "\n",
    text,
    flags=re.I,
)

# --- Replace Pixi global block with Canvas2D core (keep model/sim after) ---
OLD_BLOCK = r'''  /\*\* --- Pixi \+ sim --- \*/
  let app = null;
  let world = null;
  let layerEdges = null;
  /\*\* Single batched Graphics for all galaxy-level directory edges \(Physarum\)\. \*/
  let galaxyEdgeGfx = null;
  let galaxyEdgeFrameCounter = -1;
  /\*\* Low-end mobile iGPU: reduce fidelity; set false to restore richer visuals \(heavier GPU\)\. \*/
  const GPU_SAFE_MODE = true;
  const MAX_GALAXY_PHYSARUM_EDGES_PER_FRAME = 500;
  let layerNodes = null;
  let childrenGfx = null;
  let signalFlowGfx = null;
  let rippleGfx = null;
  /\*\* Mycelium flow: fixed pool, galaxy view only \(single batched Graphics\)\. \*/
  const MYCELIUM_POOL_SIZE = 500;
  const MYCELIUM_TOP_EDGES = 50;
  const myceliumParticlePool = \[\];
  for \(let _mi = 0; _mi < MYCELIUM_POOL_SIZE; _mi\+\+\) \{
    myceliumParticlePool\.push\(\{
      edgeIndex: 0,
      t: 0,
      speed: 0\.003,
      size: 1\.5,
      alpha: 0\.6,
      active: false,
      reverse: false,
    \}\);
  \}
  let galaxyLabelPool = \[\];
  /\*\* Rebuilt each frame in galaxy gravitational hover \(world-space hit targets for file orbit dots\)\. \*/
  let visibleChildFiles = \[\];
  /\*\* Sticky directory: keep orbit files visible while moving toward dots or during short grace period \*/
  let stickyDir = null;
  let stickyTimeout = null;
  let _gravScreenPt = null;
  let _physarumScreenPt = null;
  let bgGraphics = null;
  let starGraphics = null;
  let gridGraphics = null;
  let darkMatterGfx = null;
  let entanglementGfx = null;
  let darkMatterVisible = false;'''

NEW_BLOCK = r'''  /** --- Canvas2D renderer + sim --- */
  let canvasBg = null;
  let canvasEdges = null;
  let canvasNodes = null;
  let canvasParticles = null;
  let canvasUI = null;
  let ctxBg = null;
  let ctxEdges = null;
  let ctxNodes = null;
  let ctxParticles = null;
  let ctxUI = null;

  let pan = { x: 0, y: 0 };
  let zoom = 1;
  const ZOOM_MIN = 0.15;
  const ZOOM_MAX = 5.0;
  let targetPan = { x: 0, y: 0 };
  let targetZoom = 1;
  let edgesNodesDirty = true;
  let uiDirty = true;
  let bgDrawn = false;
  let galaxySimHotFrames = 0;

  const GPU_SAFE_MODE = true;
  const MAX_GALAXY_PHYSARUM_EDGES_PER_FRAME = 500;
  const PARTICLE_COUNT = 600;
  const particles = [];

  let galaxyLabelPool = [];
  let visibleChildFiles = [];
  let stickyDir = null;
  let stickyTimeout = null;
  let darkMatterVisible = false;

  /** Drill-down views (plain objects, no Pixi). */
  let activeStarView = null;
  let activePlanetView = null;
  let hoveredNode = null;'''

if OLD_BLOCK.replace(" ", "\\s+")  # not used
    pass

# Use simpler line-by-line marker
start = text.find("  /** --- Pixi + sim --- */")
end = text.find("  let timelineData = null;", start)
if start == -1 or end == -1:
    raise SystemExit("marker not found for pixi block")
new_mid = """  /** --- Canvas2D renderer + sim --- */
  let canvasBg = null;
  let canvasEdges = null;
  let canvasNodes = null;
  let canvasParticles = null;
  let canvasUI = null;
  let ctxBg = null;
  let ctxEdges = null;
  let ctxNodes = null;
  let ctxParticles = null;
  let ctxUI = null;

  let pan = { x: 0, y: 0 };
  let zoom = 1;
  const ZOOM_MIN = 0.15;
  const ZOOM_MAX = 5.0;
  let targetPan = { x: 0, y: 0 };
  let targetZoom = 1;
  let edgesNodesDirty = true;
  let uiDirty = true;
  let bgDrawn = false;
  let galaxySimHotFrames = 0;

  const GPU_SAFE_MODE = true;
  const MAX_GALAXY_PHYSARUM_EDGES_PER_FRAME = 500;
  const PARTICLE_COUNT = 600;
  const particles = [];

  let galaxyLabelPool = [];
  let visibleChildFiles = [];
  let stickyDir = null;
  let stickyTimeout = null;
  let darkMatterVisible = false;

  let activeStarView = null;
  let activePlanetView = null;
  let hoveredNode = null;

"""
text = text[:start] + new_mid + text[end:]

# Aliases for legacy identifiers (smoothWorld, search, etc.)
insert_after = "  let hoveredNode = null;\n\n"
if insert_after.strip() in text:
    pass
alias = """  let worldScale = 1;
  let worldTx = 0;
  let worldTy = 0;
  let targetWorldScale = 1;
  let targetWorldTx = 0;
  let targetWorldTy = 0;
  function syncPanZoomAliases() {
    worldScale = zoom;
    worldTx = pan.x;
    worldTy = pan.y;
    targetWorldScale = targetZoom;
    targetWorldTx = targetPan.x;
    targetWorldTy = targetPan.y;
  }

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

"""
# Insert aliases right after hoveredNode
text = text.replace(
    "  let hoveredNode = null;\n\n  let timelineData = null;",
    "  let hoveredNode = null;\n" + alias + "  let timelineData = null;",
    1,
)

# Remove duplicate worldScale block if present twice
text = text.replace(
    """  let worldScale = 1;
  let worldTx = 0;
  let worldTy = 0;
  let targetWorldScale = 1;
  let targetWorldTx = 0;
  let targetWorldTy = 0;

  let searchQuery""",
    """  let searchQuery""",
    1,
)

p.write_text(text, encoding="utf-8")
print("ok: block replaced")
