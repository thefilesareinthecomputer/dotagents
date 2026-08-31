import { greet } from "#lib/util";

export interface HttpOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export interface HttpError extends Error {
  status: number;
}

const buildHeaders = (extra?: Record<string, string>): Record<string, string> => {
  return {
    "content-type": "application/json",
    "x-client": greet("http"),
    ...(extra ?? {}),
  };
};

export const request = async <T>(url: string, opts: HttpOptions = {}): Promise<T> => {
  const res = await fetch(url, {
    method: opts.method ?? "GET",
    headers: buildHeaders(opts.headers),
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
  });
  if (!res.ok) {
    const err = new Error(`request failed: ${res.status}`) as HttpError;
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return (await res.json()) as T;
};

export const get = <T>(url: string, signal?: AbortSignal): Promise<T> => {
  return request<T>(url, { method: "GET", signal });
};

export const post = <T>(url: string, body: unknown): Promise<T> => {
  return request<T>(url, { method: "POST", body });
};

export const patch = <T>(url: string, body: unknown): Promise<T> => {
  return request<T>(url, { method: "PATCH", body });
};

export const del = async (url: string): Promise<void> => {
  await request<void>(url, { method: "DELETE" });
};
