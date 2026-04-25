import { describe, it, expect, beforeEach, vi } from 'vitest';
import { validateCohereKey, validateHuggingfaceKey, validateReplicateKey, validatePerplexityKey, validateCustomOpenAiCompat, makeBearerValidator, validateProviderKey } from '../../src/web/vault/validators.js';

const orig = globalThis.fetch;

describe('validators (new providers)', () => {
  beforeEach(() => {
    globalThis.fetch = orig;
    vi.restoreAllMocks();
  });

  it('makeBearerValidator: 200', async () => {
    const v = makeBearerValidator('t', 'https://example.com/x');
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
    const r = await v('k');
    expect(r.ok).toBe(true);
  });

  it('replicate: uses Token not Bearer (mock)', async () => {
    globalThis.fetch = vi.fn((u, o) => {
      expect(/** @type {any} */(o).headers?.authorization).toMatch(/^Token /);
      return Promise.resolve({ ok: true, status: 200 });
    });
    const r = await validateReplicateKey('r8_test');
    expect(r.ok).toBe(true);
  });

  it('huggingface: mock ok', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
    const r = await validateHuggingfaceKey('hf_x');
    expect(r.ok).toBe(true);
  });

  it('cohere: Bearer GET (mock)', async () => {
    globalThis.fetch = vi.fn((u, o) => {
      expect(/** @type {any} */(o).headers?.authorization).toMatch(/^Bearer /);
      return Promise.resolve({ ok: true, status: 200 });
    });
    const s = 'a'.repeat(40);
    const r = await validateCohereKey(s);
    expect(r.ok).toBe(true);
  });

  it('perplexity: post mock', async () => {
    globalThis.fetch = vi.fn((url, o) => {
      expect(/** @type {any} */(o).method).toBe('POST');
      return Promise.resolve({ ok: true, status: 200 });
    });
    const r = await validatePerplexityKey('pplx-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    expect(r.ok).toBe(true);
  });

  it('custom OpenAI: requires base URL (no fetch)', async () => {
    const r = await validateCustomOpenAiCompat('k', '');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/base URL/);
  });

  it('custom OpenAI: GET /models (mock)', async () => {
    globalThis.fetch = vi.fn((u) => {
      expect(String(u)).toContain('/models');
      return Promise.resolve({ ok: true, status: 200 });
    });
    const r = await validateCustomOpenAiCompat('k', 'https://a.example/v1');
    expect(r.ok).toBe(true);
  });

  it('validateProviderKey custom without base', async () => {
    const r = await validateProviderKey('custom_openai', 'k', {});
    expect(r.ok).toBe(false);
  });
});
