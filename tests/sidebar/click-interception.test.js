import { describe, it, expect } from 'vitest';
import { newSidebarTestWindow, readIndexHtml } from './helpers.js';

/**
 * happy-dom has no document.elementsFromPoint. For #omnix-sidebar, approximate
 * topmost hit: flex-child stack z-index (higher = on top), then deeper node wins.
 * @param {import('happy-dom').Window} win
 * @param {number} x
 * @param {number} y
 * @returns {Element[]}
 */
function elementsFromPointPolyfill(win, x, y) {
  const root = win.document.getElementById('omnix-sidebar');
  if (!root) {
    return [];
  }

  /**
   * @param {Element} el
   * @returns {number}
   */
  function sidebarChildStackZ(el) {
    let n = el;
    while (n && n !== root) {
      if (n.parentNode === root) {
        const z = win.getComputedStyle(/** @type {Element} */ (n)).zIndex;
        if (z === 'auto') {
          return 0;
        }
        const p = parseInt(z, 10);
        return Number.isNaN(p) ? 0 : p;
      }
      n = n.parentNode;
    }
    return -1;
  }

  /**
   * @param {Element} el
   * @returns {number}
   */
  function depthUnder(el) {
    let d = 0;
    let n = el;
    while (n && n !== root) {
      d += 1;
      n = n.parentNode;
    }
    return d;
  }

  const candidates = /** @type {Element[]} */ ([]);
  const all = root.querySelectorAll('*');
  for (const el of all) {
    if (typeof el.getBoundingClientRect !== 'function') {
      continue;
    }
    if (el === root) {
      continue;
    }
    const st = win.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') {
      continue;
    }
    if (st.pointerEvents === 'none') {
      continue;
    }
    const r = el.getBoundingClientRect();
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) {
      continue;
    }
    if (sidebarChildStackZ(el) < 0) {
      continue;
    }
    candidates.push(el);
  }

  const uniq = [...new Set(candidates)];
  uniq.sort((a, b) => {
    const za = sidebarChildStackZ(a);
    const zb = sidebarChildStackZ(b);
    if (zb !== za) {
      return zb - za;
    }
    return depthUnder(b) - depthUnder(a);
  });

  return uniq;
}

/** @param {Element | null} top */
function isRailHit(top) {
  if (!top) {
    return false;
  }
  if (top.id === 'omnix-sb-rail') {
    return true;
  }
  if (top.classList && top.classList.contains('sb-rail-btn')) {
    return true;
  }
  if (typeof top.closest === 'function' && top.closest('.sb-rail-btn')) {
    return true;
  }
  return false;
}

describe('rail click target (no panel hit layer over rail icons)', () => {
  it('at each icon center, top hit is rail (closed): elementsFromPoint[0] is .sb-rail-btn or .sb-ico in rail', () => {
    const win = newSidebarTestWindow({ width: 1280, html: readIndexHtml() });
    const root = win.document.getElementById('omnix-sidebar');
    expect(root?.getAttribute('data-sb-state')).toBe('closed');
    const rail = win.document.getElementById('omnix-sb-rail');
    expect(rail).not.toBeNull();
    const p = win.document.getElementById('omnix-sidebar-panel');
    const zRail = parseInt(String(win.getComputedStyle(/** @type {Element} */ (rail)).zIndex), 10) || 0;
    const zPanel = parseInt(String(p ? win.getComputedStyle(p).zIndex : '0'), 10) || 0;
    expect(zRail).toBeGreaterThan(zPanel);

    const buttons = win.document.querySelectorAll('#omnix-sb-rail .sb-rail-btn');
    expect(buttons.length).toBe(7);
    for (let i = 0; i < 7; i += 1) {
      const btn = buttons[i];
      const r = btn.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const fromPoint =
        typeof win.document.elementsFromPoint === 'function'
          ? () => win.document.elementsFromPoint(cx, cy)
          : () => elementsFromPointPolyfill(win, cx, cy);
      const list = fromPoint();
      const top0 = list[0];
      expect(
        isRailHit(top0),
        `index ${i}: top element should be rail, got ${top0?.nodeName} ${top0?.id} ${
          top0 && 'className' in top0 ? (/** @type {Element} */ (top0)).getAttribute('class') : ''
        }`,
      ).toBe(true);
    }
  });

  it('at each icon center, top hit is rail (open) — panel must not sit above the rail in 0–48px', async () => {
    const win = newSidebarTestWindow({ width: 1280, html: readIndexHtml() });
    const root = win.document.getElementById('omnix-sidebar');
    const files = win.document.querySelector('#omnix-sb-rail [data-sb-tab="files"]');
    expect(root).not.toBeNull();
    (/** @type {Element} */ (files)).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(root.getAttribute('data-sb-state')).toBe('open');
    const buttons = win.document.querySelectorAll('#omnix-sb-rail .sb-rail-btn');
    for (let i = 0; i < 7; i += 1) {
      const btn = buttons[i];
      const r = btn.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const fromPoint =
        typeof win.document.elementsFromPoint === 'function'
          ? () => win.document.elementsFromPoint(cx, cy)
          : () => elementsFromPointPolyfill(win, cx, cy);
      const list = fromPoint();
      const top0 = list[0];
      expect(
        isRailHit(top0),
        `index ${i} (open): top should be rail, got ${top0?.nodeName} ${top0?.id}`,
      ).toBe(true);
    }
  });
});
