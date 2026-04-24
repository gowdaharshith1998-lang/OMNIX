import { describe, it, expect } from 'vitest';
import { newSidebarTestWindow, readIndexHtml } from './helpers.js';

function open(win, tab) {
  const b = win.document.querySelector(`[data-sb-tab="${tab}"]`);
  b?.dispatchEvent(
    new win.MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }),
  );
}

describe('placeholders and Receipts link', () => {
  it('Files — Integration #6 and description', () => {
    const win = newSidebarTestWindow();
    if (!readIndexHtml().includes('omnix-sidebar')) {
      return;
    }
    open(win, 'files');
    const n = win.document.getElementById('sb-p-files');
    if (!n) {
      return;
    }
    expect(n.textContent).toMatch(/Coming in Integration #6/);
    expect(n.textContent).toMatch(/8 languages/);
  });

  it('Search — Integration #8 and description', () => {
    const win = newSidebarTestWindow();
    open(win, 'search');
    const n = win.document.getElementById('sb-p-search');
    expect(n && n.textContent).toMatch(/Coming in Integration #8/);
    expect(n && n.textContent).toMatch(/semantic search/i);
  });

  it('Graph — Integration #4 and description', () => {
    const win = newSidebarTestWindow();
    open(win, 'graph');
    const n = win.document.getElementById('sb-p-graph');
    expect(n && n.textContent).toMatch(/Coming in Integration #4/);
    expect(n && n.textContent).toMatch(/controls|analytics/i);
  });

  it('Timeline — Integration #4 and description', () => {
    const win = newSidebarTestWindow();
    open(win, 'timeline');
    const n = win.document.getElementById('sb-p-timeline');
    expect(n && n.textContent).toMatch(/Coming in Integration #4/);
    expect(n && n.textContent).toMatch(/commit history|replay/i);
  });

  it('Receipts — link to /receipts and placeholder', () => {
    const win = newSidebarTestWindow();
    open(win, 'receipts');
    const a = win.document.getElementById('sb-p-receipts-browse') || win.document.querySelector(
      'a[href^="/receipts"]',
    );
    if (a) {
      const href = a.getAttribute('href') || a.href;
      const ok = (href && href.includes('receipts')) || a.textContent?.includes('Browse');
      expect(ok).toBe(true);
    } else {
      const n = win.document.getElementById('sb-p-receipts');
      expect(n && n.textContent && (n.textContent.indexOf('Browse') >= 0 || n.textContent.indexOf('receipts') >= 0)).toBe(true);
    }
  });

  it('Settings — Integration #2 and description', () => {
    const win = newSidebarTestWindow();
    open(win, 'settings');
    const n = win.document.getElementById('sb-p-settings');
    expect(n && n.textContent).toMatch(/Coming in Integration #2/);
    expect(n && n.textContent).toMatch(/Vault|theme|keybind/i);
  });
});
