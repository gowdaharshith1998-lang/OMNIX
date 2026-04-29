import { describe, it, expect, afterEach, vi } from 'vitest';
import { newFindTestWindow, OMNIX_FIND_POS_KEY } from './helpers.js';

afterEach(() => {
  const ls = globalThis.localStorage;
  if (ls && typeof ls.removeItem === 'function') {
    ls.removeItem(OMNIX_FIND_POS_KEY);
  }
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/**
 * @param {import('happy-dom').Window} win
 * @param {string} type
 * @param {EventTarget} target
 * @param {number} x
 * @param {number} y
 */
function firePtr(win, type, target, x, y) {
  if (!win.PointerEvent) {
    return;
  }
  target.dispatchEvent(
    new win.PointerEvent(type, {
      bubbles: true,
      cancelable: true,
      clientX: x,
      clientY: y,
      pointerId: 1,
      button: 0,
      pointerType: 'mouse',
    }),
  );
}

function trStr(win, host) {
  if (!host) {
    return '';
  }
  return host.style.transform || win.getComputedStyle(host).transform;
}

function getHost(win) {
  return win.document.getElementById('find-box-host') || win.document.getElementById('search-panel-wrap');
}

describe('find box drag and accessibility', () => {
  it('drag handle is present, distinct from input/close, with role=button and aria-label', () => {
    const win = newFindTestWindow({ width: 900, height: 700, savedPosition: null });
    const h = win.document.querySelector('.sb-find-handle');
    const input = win.document.getElementById('search-input');
    const xbtn = win.document.getElementById('search-close');
    expect(h).not.toBeNull();
    expect(h).not.toBe(input);
    expect(h).not.toBe(xbtn);
    expect(h.getAttribute('role')).toBe('button');
    const lab = (h.getAttribute('aria-label') || '').toLowerCase();
    expect(lab.length).toBeGreaterThan(0);
    expect(lab).toContain('drag');
  });

  it('pointerdown on handle — host data-find-dragging; pointerup clears', () => {
    const win = newFindTestWindow({ width: 800, height: 600, savedPosition: null });
    const host = getHost(win);
    const h = win.document.querySelector('.sb-find-handle');
    expect(h).not.toBeNull();
    firePtr(win, 'pointerdown', h, 5, 5);
    expect(host.getAttribute('data-find-dragging')).toBe('true');
    firePtr(win, 'pointerup', win, 5, 5);
    expect(host.getAttribute('data-find-dragging')).toBeFalsy();
  });

  it('pointerdown on search input does not start drag', () => {
    const win = newFindTestWindow({ width: 800, height: 600, savedPosition: null });
    const host = getHost(win);
    const input = win.document.getElementById('search-input');
    expect(input).not.toBeNull();
    firePtr(win, 'pointerdown', input, 1, 1);
    expect(host.getAttribute('data-find-dragging')).toBeFalsy();
  });

  it('pointerdown on close X does not start drag', () => {
    const win = newFindTestWindow({ width: 800, height: 600, savedPosition: null });
    const host = getHost(win);
    const xb = win.document.getElementById('search-close');
    expect(xb).not.toBeNull();
    firePtr(win, 'pointerdown', xb, 1, 1);
    expect(host.getAttribute('data-find-dragging')).toBeFalsy();
  });

  it('handle: pointerdown + window pointermove changes transform', () => {
    const win = newFindTestWindow({ width: 1000, height: 800, savedPosition: { x: 100, y: 100 } });
    const host = getHost(win);
    const t0 = trStr(win, host);
    const h = win.document.querySelector('.sb-find-handle');
    expect(h).not.toBeNull();
    firePtr(win, 'pointerdown', h, 20, 20);
    if (win.PointerEvent) {
      win.dispatchEvent(
        new win.PointerEvent('pointermove', {
          bubbles: true,
          clientX: 200,
          clientY: 120,
          pointerId: 1,
        }),
      );
    }
    const t1 = trStr(win, host);
    expect(t1).toBeTruthy();
    expect(t1).not.toBe(t0);
    firePtr(win, 'pointerup', win.document, 200, 120);
  });

  it('pointerup after drag saves position JSON in localStorage', () => {
    const win = newFindTestWindow({ width: 900, height: 700, savedPosition: null });
    const h = win.document.querySelector('.sb-find-handle');
    firePtr(win, 'pointerdown', h, 0, 0);
    if (win.PointerEvent) {
      win.dispatchEvent(
        new win.PointerEvent('pointermove', {
          bubbles: true,
          clientX: 200,
          clientY: 150,
          pointerId: 1,
        }),
      );
    }
    firePtr(win, 'pointerup', win.document, 200, 150);
    const raw = win.localStorage.getItem(OMNIX_FIND_POS_KEY);
    expect(raw).toBeTruthy();
    const p = JSON.parse(/** @type {string} */ (raw));
    expect(Object.keys(p).sort()).toEqual(['x', 'y']);
    expect(typeof p.x).toBe('number');
    expect(typeof p.y).toBe('number');
  });

  it('localStorage with saved position — find box uses it on mount (transform / matrix)', () => {
    const p = { x: 12, y: 34 };
    const win = newFindTestWindow({ width: 1200, height: 800, savedPosition: p });
    const host = getHost(win);
    const st = trStr(win, host);
    expect(st).toMatch(/12/);
    expect(st).toMatch(/34/);
  });

  it('extreme move clamps translate to ≥8px margin inside viewport', () => {
    const win = newFindTestWindow({ width: 500, height: 400, savedPosition: { x: 0, y: 0 } });
    const h = win.document.querySelector('.sb-find-handle');
    const host = getHost(win);
    expect(h).not.toBeNull();
    const pad = 8;
    firePtr(win, 'pointerdown', h, 0, 0);
    for (let i = 0; i < 4; i += 1) {
      if (win.PointerEvent) {
        win.dispatchEvent(
          new win.PointerEvent('pointermove', {
            bubbles: true,
            clientX: 50_000,
            clientY: 50_000,
            pointerId: 1,
          }),
        );
      }
    }
    if (win.PointerEvent) {
      win.dispatchEvent(
        new win.PointerEvent('pointerup', {
          bubbles: true,
          clientX: 50_000,
          clientY: 50_000,
          pointerId: 1,
        }),
      );
    }
    const st = (host).style && (host).style.transform
      ? (host).style.transform
      : String(win.getComputedStyle(/** @type {Element} */(host)).transform);
    const m3 = st.match(/translate3d\(\s*([-0-9.]+)px\s*,\s*([-0-9.]+)px/);
    const tx = m3 ? parseFloat(m3[1], 10) : 0;
    const ty = m3 ? parseFloat(m3[2], 10) : 0;
    const w = host ? host.offsetWidth : 0;
    const h0 = host ? host.offsetHeight : 0;
    expect(tx).toBeGreaterThanOrEqual(pad - 0.1);
    expect(ty).toBeGreaterThanOrEqual(pad - 0.1);
    expect(tx + w).toBeLessThanOrEqual(win.innerWidth - pad + 0.1);
    expect(ty + h0).toBeLessThanOrEqual(win.innerHeight - pad + 0.1);
  });

  it('Escape during drag restores pre-drag transform', () => {
    const win = newFindTestWindow({ width: 900, height: 800, savedPosition: { x: 50, y: 100 } });
    const host = getHost(win);
    const before = trStr(win, host);
    const h = win.document.querySelector('.sb-find-handle');
    firePtr(win, 'pointerdown', h, 0, 0);
    if (win.PointerEvent) {
      win.dispatchEvent(
        new win.PointerEvent('pointermove', {
          bubbles: true,
          clientX: 400,
          clientY: 300,
          pointerId: 1,
        }),
      );
    }
    win.dispatchEvent(
      new win.KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true, cancelable: true }),
    );
    const after = trStr(win, host);
    expect(after).toBe(before);
  });

  it('prefers-reduced-motion: #find-box-host has no transition in computed style (none or 0s)', () => {
    const win = newFindTestWindow({ width: 800, height: 600, savedPosition: null, reducedMotion: true });
    const host = getHost(win);
    const tr = String(win.getComputedStyle(host).transition);
    if (tr && tr !== 'none' && tr !== 'all' && tr !== 'all 0s ease 0s') {
      expect(tr).toMatch(/0(?:ms|s)/);
    } else {
      expect(['none', 'all', 'all 0s ease 0s'].some((a) => tr === a) || tr.includes('0s')).toBe(true);
    }
  });
});
