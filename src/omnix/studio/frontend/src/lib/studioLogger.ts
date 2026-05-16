/**
 * Central error logging for studio paths outside React render (ticker, global trap).
 * Uses console.error (not console.log) per slice 15.2 acceptance criteria.
 */
export function logStudioError(
  scope: string,
  message: string,
  err?: unknown
): void {
  const detail =
    err instanceof Error
      ? err.stack ?? err.message
      : err !== undefined
        ? String(err)
        : "";
  console.error(`[omnix-studio:${scope}]`, message, detail);
}
