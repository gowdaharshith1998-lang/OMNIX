import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { resetAllVault } from './helpers.js';
import { createVault } from '../../src/web/vault/vault.js';
import { mountScanSection } from '../../src/web/vault/ui-scan.js';

vi.mock('../../src/web/vault/validators.js', () => ({
  validateProviderKey: vi.fn(() => Promise.resolve({ ok: true })),
}));

function defaultLabel(p) {
  if (p === 'ollama') return 'Ollama';
  return p;
}

describe('vault scan UI', () => {
  beforeEach(async () => {
    await resetAllVault();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('scan button renders in grid mount', async () => {
    const v = createVault();
    await v.init('twelvecharrr12');
    const body = document.createElement('div');
    const rr = vi.fn();
    mountScanSection(body, v, {
      requestRender: rr,
      defaultLabel,
    });
    const btn = body.querySelector('button');
    expect(btn).not.toBeNull();
    if (btn) expect(btn.textContent).toMatch(/Scan for existing keys/);
  });

  it('empty state when no detections (mocked fetch)', async () => {
    const v = createVault();
    await v.init('twelvecharr12');
    const body = document.createElement('div');
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ detections: [], receipt_path: '~/.omnix' }),
          { status: 200 },
        ),
      ),
    );
    mountScanSection(body, v, {
      requestRender: () => {},
      defaultLabel,
    });
    const btn = /** @type {HTMLButtonElement} */ (body.querySelector('button'));
    expect(btn).not.toBeNull();
    if (!btn) return;
    await btn.click();
    await vi.waitFor(
      () => {
        expect(
          (body.textContent || '').includes('No keys found'),
        ).toBe(true);
      },
      { timeout: 3000 },
    );
  });

  it('import flows through vault addKey (mocked fetch)', async () => {
    const v = createVault();
    await v.init('twelvechar_12a');
    const addSpy = vi.spyOn(v, 'addKey');
    globalThis.fetch = vi
      .fn()
      .mockImplementationOnce(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              detections: [
                {
                  detection_id: 'a1',
                  provider: 'openai',
                  source: 'env:K',
                  masked_preview: 'sk-*',
                  key_length: 10,
                  detected_at: 'x',
                },
              ],
            }),
            { status: 200 },
          ),
        ),
      )
      .mockImplementationOnce(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ ok: true, provider: 'openai', key: 'sk-test-key-openai-abc' + 'a'.repeat(20) }),
            { status: 200 },
          ),
        ),
      );
    const body = document.createElement('div');
    mountScanSection(body, v, {
      requestRender: () => {},
      defaultLabel,
    });
    const btn = /** @type {HTMLButtonElement} */ (body.querySelector('button'));
    if (!btn) return;
    await btn.click();
    await vi.waitFor(
      () => {
        const imp = Array.from(
          body.querySelectorAll('button'),
        ).find((b) => b.textContent === 'Import');
        expect(imp).toBeTruthy();
      },
      { timeout: 5000 },
    );
    const imp2 = Array.from(
      body.querySelectorAll('button'),
    ).find((b) => b.textContent === 'Import');
    if (imp2) {
      imp2.click();
    }
    await vi.waitFor(
      () => {
        expect(addSpy).toHaveBeenCalled();
      },
      { timeout: 5000 },
    );
    const arg = addSpy.mock.calls[0][0];
    expect(arg.provider).toBe('openai');
    expect(String(arg.key_value).length).toBeGreaterThan(10);
  });

  it('masked previews from server shown (mocked fetch)', async () => {
    const v = createVault();
    await v.init('twelve_mprev_12');
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            detections: [
              {
                detection_id: 'b2',
                provider: 'anthropic',
                source: 'env:Z',
                masked_preview: 'sk****tail',
                key_length: 20,
                detected_at: 't',
              },
            ],
            receipt_path: 'x',
          }),
          { status: 200 },
        ),
      ),
    );
    const body = document.createElement('div');
    mountScanSection(body, v, { requestRender: () => {}, defaultLabel });
    const btn = /** @type {HTMLButtonElement} */ (body.querySelector('button'));
    if (btn) await btn.click();
    await vi.waitFor(
      () => {
        const t = body.textContent || '';
        expect(t).toMatch(/sk\*{2,4}\*?tail/);
      },
      { timeout: 3000 },
    );
  });
});
