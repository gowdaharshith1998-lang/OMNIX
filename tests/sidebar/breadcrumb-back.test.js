import { describe, it, expect } from 'vitest';
import { readIndexHtml } from './helpers.js';

describe('breadcrumb back button', () => {
  it('has back button markup in #breadcrumb HUD', () => {
    const html = readIndexHtml();
    expect(html).toMatch(/id="breadcrumb"/);
    expect(html).toMatch(/id="bc-back"/);
    expect(html).toMatch(/aria-label="Back"/);
    // At root, button is present and disabled (no layout shift).
    expect(html).toMatch(/id="bc-back"[^>]*disabled/);
  });

  it('wires click + Cmd\\/Ctrl+[ to same goBack path as right-click', () => {
    const html = readIndexHtml();
    // Right click up-one-level on background calls goBack().
    expect(html).toMatch(/btn\s*===\s*2[\s\S]*viewLevel\s*!==\s*'galaxy'[\s\S]*goBack\(\)/);
    // Breadcrumb button click calls goBack() when applicable.
    expect(html).toMatch(/bc-back[\s\S]*onclick[\s\S]*goBack\(\)/);
    // Keyboard shortcut Cmd+[ / Ctrl+[ calls goBack().
    expect(html).toMatch(/ev\.key\s*===\s*'\['[\s\S]*\(ev\.metaKey\s*\|\|\s*ev\.ctrlKey\)[\s\S]*goBack\(\)/);
  });
});

