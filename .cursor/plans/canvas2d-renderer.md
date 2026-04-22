# CANVAS2D RENDERER PLAN

## Architecture

Five stacked transparent canvas elements, `position: fixed` / absolute over the viewport (`#graph-container`), matching the user specification.

### Layer stack (bottom → top)

| Layer | ID | Role |
|-------|-----|------|
| 0 | `canvas-bg` | Background: gradient, seeded starfield, hex grid; redraw on resize (parallax optional via `bgDirty`) |
| 1 | `canvas-edges` | Galaxy: Physarum edges (additive `lighter`), dark matter, entanglement, ripple, AI trace, orbit rings; star/planet: edge graphics |
| 2 | `canvas-nodes` | Galaxy: directory/file/class nodes + labels; star: file nodes; planet: symbol cells |
| 3 | `canvas-particles` | Galaxy: phosphor persistence + mycelium flow; star/planet: signal particles (full clear each frame) |
| 4 | `canvas-ui` | Hit target only (`pointer-events: all`); optional future UI strokes |

CSS: layers 0–3 `pointer-events: none`; layer 4 captures input.

### World transform (replaces Pixi `world` container)

- `worldScale`, `worldTx`, `worldTy` remain the canonical pan/zoom state (existing `fitWorldToNodes`, `smoothWorld`, wheel).
- `ctx.setTransform(worldScale, 0, 0, worldScale, worldTx, worldTy)` before drawing world-space galaxy content.
- `screenToWorld` / `worldToScreen` replace `world.toLocal` / `world.toGlobal`.

### Dirty flags (galaxy)

- `edgesNodesDirty`: set on simulation tick, zoom/pan, hover changes, zoom-to-search; cleared after edges + child-orbit underlay redraw.
- Star/planet: redraw each frame while simulations run or animations play (simpler than dirty coalescing).
- Galaxy particle layer: phosphor fade every frame; non-galaxy views use `clearRect` + draw.

### Innovations (per spec)

1. **Phosphor persistence** (galaxy particles): `fillRect` with `rgba(2, 6, 21, 0.88)` instead of full clear.
2. **shadowBlur glow**: nodes and particles only; reset `shadowBlur` / `shadowColor` after each draw.
3. **Additive edges** (`globalCompositeOperation = 'lighter'`) for galaxy Physarum pass; reset to `source-over`.
4. **No shadowBlur** on edges; opacity and color only.

### Star / planet (mitosis drill-down)

- No `PIXI.Container`: use plain `activeStarView` / `activePlanetView` state objects (`_sim`, `_edges`, `_nodes`, `_signalParticles`, `_growthPhaseComplete`, `_growthTl`, etc.).
- Each star/planet node uses a **display object** `{ x, y, scale: {x,y}, alpha }` for GSAP (replaces `container.position` / `container.scale` / `container.alpha`).
- `drawStarGrowthEdges`, `drawSubviewPhysarumEdges`, signal particles, and node shapes are implemented with Canvas2D in the render loop.
- Cleanup removes state and references; no `destroy()`.

### Preserved (unchanged intent)

- `buildGraphModel`, fetch `/api/graph`, d3-force, GSAP timelines, sidebar/X-Ray, timeline, dark matter toggle, search, breadcrumb, stats, AI agents, buttons.

### Removed

- PixiJS CDN and every `PIXI.*` usage.
- WebGL canvas; no `webglcontextlost` path required for the graph (Canvas2D only).

### Constraints

- No `setInterval` for animation; `requestAnimationFrame` only.
- No new CDN dependencies.
- If `simulation.alpha() > 0.001` for more than 500 frames while ticking, force-stop the simulation.
- Do not use `ctx.filter = blur()` on hot paths.

### Verification

- `grep -c "PIXI\\." src/web/index.html` → `0`
- Manual: galaxy glow, edges, particles, pan/zoom, drill-down, X-Ray, no WebGL context loss.
