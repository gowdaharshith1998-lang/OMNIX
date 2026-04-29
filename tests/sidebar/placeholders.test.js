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
    const list = win.document.getElementById('sb-receipts-list');
    const status = win.document.getElementById('sb-receipts-status');
    expect(list).not.toBeNull();
    expect(status).not.toBeNull();
    const n = win.document.getElementById('sb-p-receipts');
    expect(n && n.textContent).not.toMatch(/Coming in Integration/i);
  });

  it('Settings — Integration #2 and description', () => {
    const win = newSidebarTestWindow();
    open(win, 'settings');
    const n = win.document.getElementById('sb-p-settings');
    expect(n && n.textContent).toMatch(/Coming in Integration #2/);
    expect(n && n.textContent).toMatch(/Vault|theme|keybind/i);
  });
});
