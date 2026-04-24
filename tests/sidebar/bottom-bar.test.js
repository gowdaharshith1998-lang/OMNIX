import { describe, it, expect } from 'vitest';
import { readIndexHtml } from './helpers.js';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const EXPECTED_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  'fixtures/bottom-bar-expected.html',
);

const BOTTOM_BAR_EXPECTED = readFileSync(EXPECTED_PATH, 'utf8');

function norm(s) {
  return s
    .replace(/>\s+</g, '><')
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .join('');
}

/**
 * @param {string} html
 * @returns {string}
 */
function extractBottomBarOuterHtml(html) {
  const m = String(html).match(
    /<div class="hud glass" id="bottom-bar"[\s\S]*?<\/div>\s*(?=[\n\r]|<)/,
  );
  return m ? m[0].trim() : '';
}

describe('bottom bar (Integration #3.6)', () => {
  it('index.html #bottom-bar matches snapshot (no AI Keys; order preserved)', () => {
    const h = readIndexHtml();
    const a = norm(extractBottomBarOuterHtml(h));
    const b = norm(BOTTOM_BAR_EXPECTED);
    expect(a).toBe(b);
  });

  it('bottom bar does not include AI Keys text or btn-vault', () => {
    const h = readIndexHtml();
    const bar = extractBottomBarOuterHtml(h);
    expect(bar.toLowerCase().includes('ai keys')).toBe(false);
    expect(bar.includes('btn-vault')).toBe(false);
  });

  it('separate hidden #btn-vault exists for vault module (not in bottom bar)', () => {
    const h = readIndexHtml();
    expect(h.includes('id="btn-vault"')).toBe(true);
    expect(h.includes('id="btn-vault"') && h.includes('hidden')).toBe(true);
    const bar = extractBottomBarOuterHtml(h);
    expect(bar.includes('btn-vault')).toBe(false);
  });

  it('bottom bar is a single flex row; height rule unchanged (padding 10px 16px in stylesheet)', () => {
    const h = readIndexHtml();
    expect(h).toMatch(/#bottom-bar[\s\S]*?display:\s*flex/);
    expect(h).toMatch(/#bottom-bar[\s\S]*?padding:\s*10px\s*16px/);
  });
});
