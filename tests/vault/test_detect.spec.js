import { describe, it, expect } from 'vitest';
import { detectProvider, PROVIDERS } from '../../src/web/vault/providers.js';

describe('detectProvider', () => {
  it('test_detect_anthropic_exact', () => {
    const r = detectProvider(
      'sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    );
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['anthropic']);
  });

  it('test_detect_openai_exact', () => {
    const r = detectProvider('sk-proj-aaaaaaaaaaaaaaaaaaaaaaaaa');
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['openai']);
  });

  it('test_detect_google_exact', () => {
    const r = detectProvider(
      'AIzaSyDOCAbC1234567890aBcDeFgHiJkLmNoPqRsT',
    );
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['google']);
  });

  it('test_detect_xai_exact', () => {
    const r = detectProvider('xai-' + 'a'.repeat(40));
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['xai']);
  });

  it('test_detect_groq_exact', () => {
    const r = detectProvider('gsk_' + 'a'.repeat(50));
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['groq']);
  });

  it('test_detect_openrouter_exact', () => {
    const r = detectProvider('sk-or-v1-' + 'a'.repeat(50));
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['openrouter']);
  });

  it('test_detect_huggingface_exact', () => {
    const r = detectProvider('hf_' + 'a'.repeat(35));
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['huggingface']);
  });

  it('test_detect_ambiguous_sk', () => {
    const s = 'sk-' + 'a'.repeat(32);
    const r = detectProvider(s);
    const ids = r.matches.map((m) => m.id);
    expect(ids).toContain('openai');
    expect(ids).toContain('deepseek');
    expect(r.confidence).toBe('ambiguous');
  });

  it('test_detect_unknown_returns_none', () => {
    const r = detectProvider('totally-random-string-xyz-12345');
    expect(r.confidence).toBe('none');
    expect(r.matches.length).toBe(0);
  });

  it('test_detect_empty_string', () => {
    const r = detectProvider('');
    expect(r.confidence).toBe('none');
    expect(r.matches.length).toBe(0);
  });

  it('test_detect_url_recognized_as_ollama', () => {
    const r = detectProvider('http://localhost:11434');
    expect(r.confidence).toBe('exact');
    expect(r.matches.map((m) => m.id)).toEqual(['ollama']);
  });

  it('test_custom_openai_never_auto_detected', () => {
    const r = detectProvider('any-string');
    const hasCustom = r.matches.some((m) => m.id === 'custom_openai');
    expect(hasCustom).toBe(false);
  });

  it('test_provider_catalog_has_all_required', () => {
    expect(Object.keys(PROVIDERS).length).toBeGreaterThanOrEqual(16);
  });
});
