import { describe, it, expect } from 'vitest';
import { newSidebarTestWindow } from './helpers.js';

describe('activity rail', () => {
  it('renders 48px wide rail on left edge', () => {
    const win = newSidebarTestWindow();
    const root = win.document.getElementById('omnix-sidebar');
    const rail = win.document.getElementById('omnix-sb-rail');
    expect(root).not.toBeNull();
    expect(rail).not.toBeNull();
    const w = parseFloat(String(win.getComputedStyle(rail).width || 0).replace('px', '')) || 0;
    expect(w === 48 || rail.getBoundingClientRect().width === 48).toBe(true);
  });

  it('renders 7 icons in order: files → settings', () => {
    const win = newSidebarTestWindow();
    const order = [
      'files',
      'search',
      'graph',
      'timeline',
      'providers',
      'receipts',
      'settings',
    ];
    const tabs = win.document.querySelectorAll('#omnix-sb-rail [data-sb-tab]');
    expect(tabs.length).toBe(7);
    for (let i = 0; i < 7; i += 1) {
      expect(tabs[i].getAttribute('data-sb-tab')).toBe(order[i]);
    }
  });

  it('tooltip with tab label is hidden until 150ms after hover, then shows; hides on mouseout', async () => {
    const win = newSidebarTestWindow();
    const b = win.document.querySelector('#omnix-sb-rail [data-sb-tab="files"]');
    const tip = win.document.getElementById('omnix-sb-tooltip');
    expect(b).not.toBeNull();
    expect(tip).not.toBeNull();
    b.dispatchEvent(
      new win.MouseEvent('mouseenter', { bubbles: true, cancelable: true }),
    );
    expect(tip.classList.contains('is-visible')).toBe(false);
    await new Promise((r) => setTimeout(r, 5));
    expect(tip.classList.contains('is-visible')).toBe(false);
    await new Promise((r) => setTimeout(r, 200));
    const nowVis = tip.getAttribute('aria-hidden') === 'false' && tip.classList.contains('is-visible');
    expect(nowVis).toBe(true);
    b.dispatchEvent(
      new win.MouseEvent('mouseleave', { bubbles: true, cancelable: true }),
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(
      (tip.getAttribute('aria-hidden') || '') === 'true' || !tip.classList.contains('is-visible'),
    ).toBe(true);
  });
});
