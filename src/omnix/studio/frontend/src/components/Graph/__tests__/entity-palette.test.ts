import { describe, expect, it } from 'vitest';
import { ENTITY_PALETTE, FALLBACK_COLOR, colorForType } from '../entityPalette';

describe('entity palette (slice-19)', () => {
  it('registers all seven entity types', () => {
    const keys = Object.keys(ENTITY_PALETTE);
    expect(keys.sort()).toEqual(
      ['code', 'decision', 'document', 'people', 'process', 'thread', 'ticket'].sort(),
    );
  });

  it('hex values match spec', () => {
    expect(ENTITY_PALETTE.code).toBe('#5eead4');
    expect(ENTITY_PALETTE.people).toBe('#fbbf24');
    expect(ENTITY_PALETTE.decision).toBe('#d8b4fe');
    expect(ENTITY_PALETTE.thread).toBe('#a5b4fc');
    expect(ENTITY_PALETTE.ticket).toBe('#fb923c');
    expect(ENTITY_PALETTE.document).toBe('#5fa3ff');
    expect(ENTITY_PALETTE.process).toBe('#34d399');
  });

  it('returns fallback for unknown type', () => {
    expect(colorForType('__unknown_slice19__')).toBe(FALLBACK_COLOR);
    expect(FALLBACK_COLOR).toBe('#9ca3af');
  });
});
