import { describe, it, expect, afterEach } from 'vitest';
import { newFindTestWindow, OMNIX_FIND_POS_KEY, readIndexHtml, parseIndexBodyDom } from './helpers.js';

/**
 * @param {import('happy-dom').Window} win
 * @param {number} w
 * @param {number} h
 */
function setFindVwVhForHappyDom(win, w, h) {
  const el = win.document.getElementById('find-box-host');
  if (el) {
    el.setAttribute('data-omnix-vw', String(w));
    el.setAttribute('data-omnix-vh', String(h));
  }
}

afterEach(() => {
  const ls = globalThis.localStorage;
  if (ls && typeof ls.removeItem === 'function') {
    ls.removeItem(OMNIX_FIND_POS_KEY);
  }
});

const GAP = 16;
const BOTTOM_DOCK = 20;

/**
 * @param {import('happy-dom').Window} win
 * @param {Element | null} el
 * @returns {{ x: number, y: number }}
 */
function parseTranslate3d(win, el) {
  if (!el) {
    return { x: 0, y: 0 };
  }
  const t = (el).style && (el).style.transform
    ? (el).style.transform
    : String(win.getComputedStyle(el).transform);
  const m3 = t.match(/translate3d\(\s*([-0-9.]+)px\s*,\s*([-0-9.]+)px/);
  if (m3) {
    return { x: parseFloat(m3[1], 10), y: parseFloat(m3[2], 10) };
  }
  const m2d6 = t.match(
    /matrix\(\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*\)/,
  );
  if (m2d6) {
    return { x: parseFloat(m2d6[5], 10), y: parseFloat(m2d6[6], 10) };
  }
  const m2 = t.match(/matrix\(([^)]+)\)/);
  if (m2) {
    const p = m2[1].split(/,\s*/);
    if (p.length >= 6) {
      return { x: parseFloat(p[4], 10), y: parseFloat(p[5], 10) };
    }
  }
  return { x: 0, y: 0 };
}

function getHost(win) {
  return win.document.getElementById('find-box-host') || win.document.getElementById('search-panel-wrap');
}

/** Same width fallbacks as OMNIX find IIFE getHostSize (happy-dom often has offsetWidth 0 with no layout). */
function hostContentWidth(/** @type {Element | null} */ el) {
  if (!el) {
    return 0;
  }
  const ow = (el).offsetWidth || 0;
  if (ow > 0) {
    return ow;
  }
  const r = (el).getBoundingClientRect && (el).getBoundingClientRect();
  if (r && r.width) {
    return r.width;
  }
  return 300;
}

describe('find box default position and resize', () => {
  it('readIndex: #find-box-host is present in markup', () => {
    const doc = parseIndexBodyDom(readIndexHtml());
    expect(doc.getElementById('find-box-host')).not.toBeNull();
  });

  it('newFindTestWindow sets data-omnix-vw on #find-box-host (test harness only)', () => {
    const win = newFindTestWindow({ width: 920, height: 700, savedPosition: null });
    const h = win.document.getElementById('find-box-host');
    expect(h).not.toBeNull();
    expect(h.getAttribute('data-omnix-vw')).toBe('920');
    expect(h.getAttribute('data-omnix-vh')).toBe('700');
  });

  it('first load (no localStorage): find box is horizontally centered (from translate x)', () => {
    const w = 920;
    const h = 700;
    const win = newFindTestWindow({ width: w, height: h, savedPosition: null });
    const host = getHost(win);
    expect(host).not.toBeNull();
    const vw = Number(host.getAttribute('data-omnix-vw') || 0) || w;
    expect(win.localStorage.getItem(OMNIX_FIND_POS_KEY)).toBeNull();
    const p = parseTranslate3d(win, host);
    const mid = vw / 2;
    const iw = hostContentWidth(/** @type {Element} */(host));
    const boxCenter = p.x + iw / 2;
    expect(Math.abs(boxCenter - mid)).toBeLessThan(1.5);
  });

  it('first load: 16px gap from translate y, bottom bar height, and host height (happy-dom: no layout rects)', () => {
    const w = 900;
    const h = 750;
    const win = newFindTestWindow({ width: w, height: h, savedPosition: null });
    const host = getHost(win);
    const bar = win.document.getElementById('bottom-bar');
    expect(host).not.toBeNull();
    expect(bar).not.toBeNull();
    const p = parseTranslate3d(win, host);
    const ih = host ? host.offsetHeight : 0;
    const barH = bar ? bar.offsetHeight : 0;
    const yBottom = p.y + ih;
    const expectedBarTop = h - BOTTOM_DOCK - barH;
    const gap = expectedBarTop - yBottom;
    expect(gap).toBeGreaterThanOrEqual(GAP - 1.5);
    expect(gap).toBeLessThanOrEqual(GAP + 1.5);
  });

  it('viewport resize with no saved position: re-centers horizontally (translate x)', () => {
    const win = newFindTestWindow({ width: 800, height: 600, savedPosition: null });
    const host = getHost(win);
    Object.defineProperty(win, 'innerWidth', { value: 1200, configurable: true, writable: true });
    try {
      win.outerWidth = 1200;
    } catch {
      /* */
    }
    setFindVwVhForHappyDom(win, 1200, 600);
    win.dispatchEvent(new win.Event('resize', { bubbles: true }));
    const p = parseTranslate3d(win, host);
    const vw = Number((/** @type {Element} */(host)).getAttribute('data-omnix-vw') || 0) || 1200;
    const mid = vw / 2;
    const iw = hostContentWidth(/** @type {Element} */(host));
    const boxCenter = p.x + iw / 2;
    expect(Math.abs(boxCenter - mid)).toBeLessThan(1.5);
  });

  it('viewport resize with saved custom position: keeps translate (x,y) in style when still in-bounds', () => {
    const saved = { x: 44, y: 120 };
    const win = newFindTestWindow({ width: 1000, height: 800, savedPosition: saved });
    const host = getHost(win);
    const t1 = (host).style && (host).style.transform
      ? (host).style.transform
      : String(win.getComputedStyle(/** @type {Element} */(host)).transform);
    Object.defineProperty(win, 'innerWidth', { value: 1200, configurable: true, writable: true });
    try {
      win.outerWidth = 1200;
    } catch {
      /* */
    }
    setFindVwVhForHappyDom(win, 1200, 800);
    win.dispatchEvent(new win.Event('resize', { bubbles: true }));
    const t2 = (host).style && (host).style.transform
      ? (host).style.transform
      : String(win.getComputedStyle(/** @type {Element} */(host)).transform);
    expect(t1).toMatch(/44/);
    expect(t1).toMatch(/120/);
    expect(t2).toMatch(/44/);
    expect(t2).toMatch(/120/);
  });
});
