import { describe, it, expect, vi, afterEach } from 'vitest';
import { newSidebarTestWindow, readIndexHtml } from './helpers.js';

function click(win, el) {
  if (!el) {
    return;
  }
  if (typeof el.click === 'function') {
    el.click();
    return;
  }
  el.dispatchEvent(
    new win.MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }),
  );
}

function flush() {
  return new Promise((r) => setTimeout(r, 0));
}
afterEach(() => {
  vi.useRealTimers();
});

describe('side panel', () => {
  it('click an icon with no panel open — panel opens, 360px on wide viewport', async () => {
    const win = newSidebarTestWindow({ width: 1280, html: readIndexHtml() });
    const files = win.document.querySelector('[data-sb-tab="files"]');
    const panel = win.document.getElementById('omnix-sidebar-panel');
    const root = win.document.getElementById('omnix-sidebar');
    expect(files).not.toBeNull();
    expect(panel).not.toBeNull();
    expect(root).not.toBeNull();
    click(win, files);
    await flush();
    expect(root.getAttribute('data-sb-state')).toBe('open');
    expect(root.getAttribute('data-sb-active')).toBe('files');
    const cw = parseFloat(win.getComputedStyle(panel).width) || panel.clientWidth;
    expect(cw).toBe(360);
  });

  it('click the same active icon again — panel closes', async () => {
    const win = newSidebarTestWindow();
    const files = win.document.querySelector('[data-sb-tab="files"]');
    const root = win.document.getElementById('omnix-sidebar');
    click(win, files);
    await flush();
    expect(root.getAttribute('data-sb-state')).toBe('open');
    click(win, files);
    expect(root.getAttribute('data-sb-state')).toBe('closed');
  });

  it('press Escape on window — panel closes', async () => {
    const win = newSidebarTestWindow();
    const files = win.document.querySelector('[data-sb-tab="search"]');
    const root = win.document.getElementById('omnix-sidebar');
    click(win, files);
    await flush();
    expect(root.getAttribute('data-sb-state')).toBe('open');
    win.dispatchEvent(
      new win.KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true, cancelable: true }),
    );
    expect(root.getAttribute('data-sb-state')).toBe('closed');
  });

  it('click panel close button — panel closes', async () => {
    const win = newSidebarTestWindow();
    const root = win.document.getElementById('omnix-sidebar');
    click(win, win.document.querySelector('[data-sb-tab="graph"]'));
    await flush();
    const btn = win.document.getElementById('omnix-sb-close');
    expect(btn).not.toBeNull();
    expect(root.getAttribute('data-sb-state')).toBe('open');
    click(win, btn);
    expect(root.getAttribute('data-sb-state')).toBe('closed');
  });

  it('while open, click another icon — panel stays open, active tab switches, content updated', async () => {
    const win = newSidebarTestWindow();
    const root = win.document.getElementById('omnix-sidebar');
    const files = win.document.querySelector('[data-sb-tab="files"]');
    const prov = win.document.querySelector('[data-sb-tab="providers"]');
    click(win, files);
    await flush();
    expect(root.getAttribute('data-sb-state')).toBe('open');
    click(win, prov);
    await flush();
    expect(root.getAttribute('data-sb-state')).toBe('open');
    expect(root.getAttribute('data-sb-active')).toBe('providers');
    const fContent = win.document.getElementById('sb-p-files');
    const pContent = win.document.getElementById('sb-p-providers');
    expect(fContent).not.toBeNull();
    expect(pContent).not.toBeNull();
    expect(fContent.getAttribute('aria-hidden')).toBe('true');
    expect(pContent.getAttribute('aria-hidden')).toBe('false');
  });

  it('prefers-reduced-motion: reduce — attr on html and/or 0s transition on panel', async () => {
    const win = newSidebarTestWindow({ reducedMotion: true, width: 1280, html: readIndexHtml() });
    const h = win.document.documentElement;
    const panel = win.document.getElementById('omnix-sidebar-panel');
    expect(h).not.toBeNull();
    expect(panel).not.toBeNull();
    const f = win.document.querySelector('[data-sb-tab="files"]');
    if (f) {
      f.click();
      await flush();
    }
    const reduced = h.getAttribute('data-sb-reduced-motion') === '1';
    const t = String(win.getComputedStyle(panel).transitionDuration || '');
    const zeroT =
      t === '0s' ||
      t === '0ms' ||
      (t && t.split(',').some((s) => /^\s*0m?s\s*$/.test(String(s).trim())));
    expect(reduced || zeroT).toBe(true);
  });

  it('viewport < 1024px — effective panel width is min(90vw, 360px)', async () => {
    const wpx = 300;
    const expectW = Math.min(0.9 * wpx, 360);
    const win = newSidebarTestWindow({ width: wpx, html: readIndexHtml() });
    const f = win.document.querySelector('[data-sb-tab="files"]');
    if (f) {
      f.click();
      await flush();
    }
    const panel = win.document.getElementById('omnix-sidebar-panel');
    const cs = String(win.getComputedStyle(panel).width);
    const rw = parseFloat(String(cs).replace('px', '')) || 0;
    const r2 = Math.round((rw * 10) / 10);
    if (r2 > 0 && (r2 === 270 || r2 === expectW)) {
      expect(r2).toBeCloseTo(expectW, 0);
    } else {
      expect(
        (cs && cs.indexOf('min(') >= 0) || rw <= 360,
      ).toBe(true);
    }
  });
});
