import { RunSummary } from "@relay/types";

export function formatRunLine(run: RunSummary): string {
  const status = run.failed > 0 ? "FAILED" : "ok";
  return `${status}  ${run.goal} (${run.completed} done, ${run.failed} failed, stop: ${run.stopped})`;
}

export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

export function formatElapsed(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 90) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
}

export const statusColor = (failed: number): string =>
  failed > 0 ? "var(--danger)" : "var(--ok)";
