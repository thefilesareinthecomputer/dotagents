export interface RunSummary {
  goal: string;
  completed: number;
  failed: number;
  stopped: string;
}

export interface MemoryHit {
  key: string;
  kind: string;
  body: string;
}

export interface RouteEntry {
  method: string;
  path: string;
  handler: string;
}

export interface ConfigView {
  model: string;
  max_steps: number;
  token_budget: number;
  server_port: number;
  log_level: string;
  tools: string[] | "all";
}

export type FetchState = "idle" | "loading" | "loaded" | "error";

export interface ApiError {
  status: number;
  message: string;
}

export type Result<T> =
  | { ok: true; value: T }
  | { ok: false; error: ApiError };
