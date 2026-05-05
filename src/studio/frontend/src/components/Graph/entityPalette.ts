/** Company-brain entity-type colors (mirror src/graph/exporter.py). No wiring into viewerEngine yet (hex densification slice). */

export const ENTITY_PALETTE = {
  code: '#5eead4',
  people: '#fbbf24',
  decision: '#d8b4fe',
  thread: '#a5b4fc',
  ticket: '#fb923c',
  document: '#5fa3ff',
  process: '#34d399',
} as const;

export const FALLBACK_COLOR = '#9ca3af';

export type EntityType = keyof typeof ENTITY_PALETTE;

export function colorForType(type: string): string {
  return (ENTITY_PALETTE as Record<string, string>)[type] ?? FALLBACK_COLOR;
}
