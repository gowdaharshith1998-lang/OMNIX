export async function* chunkText(
  fullText: string,
  chunkSize = 20,
  intervalMs = 50,
  signal?: AbortSignal
): AsyncIterable<string> {
  let cursor = 0;
  while (cursor < fullText.length) {
    if (signal?.aborted) return;
    cursor = Math.min(fullText.length, cursor + chunkSize);
    yield fullText.slice(0, cursor);
    if (cursor < fullText.length) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, intervalMs));
    }
  }
}

export function splitCodeFences(text: string): Array<{ kind: "text" | "code"; text: string }> {
  const parts: Array<{ kind: "text" | "code"; text: string }> = [];
  const re = /```(?:[^\n`]*)?\n?([\s\S]*?)```/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) != null) {
    if (match.index > last) {
      parts.push({ kind: "text", text: text.slice(last, match.index) });
    }
    parts.push({ kind: "code", text: match[1] ?? "" });
    last = re.lastIndex;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts.length ? parts : [{ kind: "text", text }];
}
