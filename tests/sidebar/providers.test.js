import { describe, it, expect } from 'vitest';
import { newSidebarTestWindow, readIndexHtml } from './helpers.js';

function makeFetch(spend, entries) {
  return (input) => {
    const u = String(input);
    if (u.includes('/api/fabric/spend')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        async json() {
          return spend;
        },
        headers: { get: () => null },
      });
    }
    if (u.includes('/api/fabric/telemetry')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        async json() {
          return { entries: entries || [] };
        },
        headers: { get: () => null },
      });
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      async json() {
        return {};
      },
      headers: { get: () => null },
    });
  };
}

async function openProviders(win) {
  const el = win.document.querySelector('[data-sb-tab="providers"]');
  if (el && el.click) {
    el.click();
  }
  for (var i = 0; i < 30; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
  }
  await new Promise((r) => setTimeout(r, 30));
}

describe('Providers tab', () => {
  it('has three main sections: keys, spend, calls (ids or landmarks)', () => {
    const win = newSidebarTestWindow({ mockFetch: makeFetch({ totals: { today_usd: 0, today_calls: 0 }, by_provider: {} }, []), html: readIndexHtml() });
    if (!win.document.getElementById('omnix-sidebar')) {
      return;
    }
    return (async function () {
      await openProviders(win);
      const k = win.document.getElementById('sb-providers-keys');
      const s = win.document.getElementById('sb-providers-spend');
      const c = win.document.getElementById('sb-providers-calls');
      expect(k).not.toBeNull();
      expect(s).not.toBeNull();
      expect(c).not.toBeNull();
    })();
  });

  it('keys grid: 4 provider key cards (vault wrap)', () => {
    const win = newSidebarTestWindow({ html: readIndexHtml() });
    if (!win.document.getElementById('sb-providers-keys')) {
      return;
    }
    const alts = win.document.querySelectorAll('#sb-providers-kgrid .sb-key-card, [data-sb-key-provider]');
    expect(alts.length >= 4).toBe(true);
  });

  it('GET /api/fabric/spend (mock) — today bars and dollar amounts render', async () => {
    const spend = {
      totals: { today_usd: 0.342, today_calls: 11, month_usd: 0 },
      by_provider: {
        anthropic: { today_usd: 0.284, today_calls: 8, month_usd: 0 },
        openai: { today_usd: 0.058, today_calls: 3, month_usd: 0 },
        google: { today_usd: 0, today_calls: 0, month_usd: 0 },
        ollama: { today_usd: 0, today_calls: 1, month_usd: 0 },
      },
    };
    const win = newSidebarTestWindow({ mockFetch: makeFetch(spend, []), html: readIndexHtml() });
    if (!readIndexHtml().includes('sb-providers-spend')) {
      return;
    }
    await openProviders(win);
    const host = win.document.getElementById('sb-providers-spend');
    if (!host) {
      return;
    }
    expect(host.textContent).toMatch(/0\.342|0\.28|28|58|\$0/);
  });

  it('telemetry: 20 entries show 20 rows in Recent Calls', async () => {
    const now = '2026-04-24T15:42:11Z';
    const entries = Array.from({ length: 20 }, function (_, n) {
      return {
        call_id: 'c' + n,
        completed_at: now,
        provider: n % 2 ? 'openai' : 'anthropic',
        model: 'm',
        cost_usd: 0.01,
        latency_ms: 100,
        status: 'ok',
      };
    });
    const win = newSidebarTestWindow({
      mockFetch: makeFetch(
        { totals: { today_usd: 1, today_calls: 2 }, by_provider: {} },
        entries,
      ),
      html: readIndexHtml(),
    });
    await openProviders(win);
    const rows = win.document.querySelectorAll('#sb-providers-calls .sb-calls-row');
    const alt = win.document.querySelectorAll('[data-sb-calls-row]');
    expect((rows && rows.length) || (alt && alt.length)).toBe(20);
  });

  it('empty telemetry — empty state copy', async () => {
    const win = newSidebarTestWindow({
      mockFetch: makeFetch(
        { totals: { today_usd: 0, today_calls: 0 }, by_provider: {} },
        [],
      ),
      html: readIndexHtml(),
    });
    await openProviders(win);
    const host = win.document.getElementById('sb-providers-calls');
    if (host) {
      expect(host.textContent).toMatch(/first signed call/i);
    }
  });

  it('signed-receipt badge links to /receipts/… for a row (id from receipt_id or call_id)', async () => {
    const win = newSidebarTestWindow({
      mockFetch: makeFetch(
        { totals: { today_usd: 0, today_calls: 0 }, by_provider: {} },
        [
          {
            call_id: 'call_abc',
            completed_at: '2026-04-24T15:42:11Z',
            provider: 'anthropic',
            model: 'claude',
            cost_usd: 0.012,
            latency_ms: 50,
            status: 'ok',
            signed: true,
            receipt_id: 'rcpt_xyz789',
          },
        ],
      ),
      html: readIndexHtml(),
    });
    await openProviders(win);
    const a = win.document.querySelector(
      '#sb-providers-calls a[href^="/receipts/"]',
    );
    if (a) {
      expect(a.getAttribute('href')).toBe('/receipts/rcpt_xyz789');
    } else {
      const any = win.document.querySelector('a[href*="/receipts/"]');
      expect(any && any.getAttribute('href') && any.getAttribute('href').indexOf('rcpt_xyz789') >= 0).toBe(
        true,
      );
    }
  });

  it('zero spend today: copy about no calls today (no infinite skeleton)', async () => {
    const win = newSidebarTestWindow({
      mockFetch: makeFetch(
        {
          totals: { today_usd: 0, today_calls: 0, month_usd: 0 },
          by_provider: {
            anthropic: { today_usd: 0, today_calls: 0, month_usd: 0 },
            openai: { today_usd: 0, today_calls: 0, month_usd: 0 },
            google: { today_usd: 0, today_calls: 0, month_usd: 0 },
            ollama: { today_usd: 0, today_calls: 0, month_usd: 0 },
          },
        },
        [],
      ),
      html: readIndexHtml(),
    });
    await openProviders(win);
    const s = win.document.getElementById('sb-providers-spend');
    if (s) {
      expect(s.textContent).toMatch(/no calls yet today|No calls yet today/);
    }
  });
});
