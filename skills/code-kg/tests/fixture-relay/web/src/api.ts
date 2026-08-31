import { ConfigView, MemoryHit, Result, RunSummary } from "@relay/types";

const BASE = "/api";

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<Result<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.text();
      return {
        ok: false,
        error: { status: res.status, message: detail.slice(0, 300) },
      };
    }
    return { ok: true, value: (await res.json()) as T };
  } catch (err) {
    return {
      ok: false,
      error: { status: 0, message: String(err) },
    };
  }
}

export function getHealth(): Promise<Result<{ status: string }>> {
  return request("GET", "/health");
}

export function getConfig(): Promise<Result<{ config: ConfigView }>> {
  return request("GET", "/config");
}

export function searchMemory(
  query: string,
): Promise<Result<{ hits: MemoryHit[] }>> {
  return request("GET", `/memory/search?q=${encodeURIComponent(query)}`);
}

export function startRun(goal: string): Promise<Result<RunSummary>> {
  return request("POST", "/runs", { goal });
}

export function latestRun(): Promise<Result<{ key: string; body: string }>> {
  return request("GET", "/runs/latest");
}
