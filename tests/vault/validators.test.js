import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  validateAnthropicKey,
  validateOpenAiKey,
  validateGoogleKey,
  validateOllamaBase,
} from '../../src/web/vault/validators.js';

const orig = globalThis.fetch;

describe('validators', () => {
  beforeEach(() => {
    globalThis.fetch = orig;
    vi.restoreAllMocks();
  });

  it('anthropic: 200 ok', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => ({}) }),
    );
    const r = await validateAnthropicKey('k');
    expect(r.ok).toBe(true);
  });

  it('anthropic: 401', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 401 }));
    const r = await validateAnthropicKey('k');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/401/);
  });

  it('openai: 200 ok', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
    const r = await validateOpenAiKey('sk');
    expect(r.ok).toBe(true);
  });

  it('openai: network error', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('net')));
    const r = await validateOpenAiKey('sk');
    expect(r.ok).toBe(false);
  });

  it('google: 200 ok', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
    const r = await validateGoogleKey('AIza');
    expect(r.ok).toBe(true);
  });

  it('ollama: 200 ok', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
    const r = await validateOllamaBase('http://127.0.0.1:11434');
    expect(r.ok).toBe(true);
  });
});
