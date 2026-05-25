/**
 * Galaxy-view background: subtle particle dot field + faint grid.
 * Drawn into a caller-owned PIXI.Graphics. Deterministic via seed
 * so resize redraws don't re-randomize the field jarringly.
 */
import * as PIXI from 'pixi.js';

const GRID_COLOR = 0x1e3a5f;
const GRID_ALPHA = 0.16;
const GRID_STEP_PX = 64;

const DOT_COLOR = 0xa5b4fc;
const DOT_AREA_PER_PIXEL = 12000;
const DOT_MIN_RADIUS = 0.6;
const DOT_MAX_RADIUS = 1.5;
const DOT_MIN_ALPHA = 0.18;
const DOT_MAX_ALPHA = 0.42;

function mulberry32(a: number): () => number {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function drawGalaxyBackground(
  g: PIXI.Graphics,
  width: number,
  height: number,
  seed: number = 0x6261636b,
): void {
  g.clear();
  if (width <= 0 || height <= 0) return;

  g.lineStyle(1, GRID_COLOR, GRID_ALPHA);
  for (let x = 0; x <= width; x += GRID_STEP_PX) {
    g.moveTo(x, 0);
    g.lineTo(x, height);
  }
  for (let y = 0; y <= height; y += GRID_STEP_PX) {
    g.moveTo(0, y);
    g.lineTo(width, y);
  }
  g.lineStyle(0);

  const rand = mulberry32(seed >>> 0);
  const dotCount = Math.floor((width * height) / DOT_AREA_PER_PIXEL);
  for (let i = 0; i < dotCount; i++) {
    const x = rand() * width;
    const y = rand() * height;
    const r = DOT_MIN_RADIUS + rand() * (DOT_MAX_RADIUS - DOT_MIN_RADIUS);
    const a = DOT_MIN_ALPHA + rand() * (DOT_MAX_ALPHA - DOT_MIN_ALPHA);
    g.beginFill(DOT_COLOR, a);
    g.drawCircle(x, y, r);
    g.endFill();
  }
}
