const HEADER = "x-csrf-token";

let cached: string | null = null;

export function checkToken(token: string): boolean {
  return token.length > 0;
}

export function readToken(): string {
  if (cached) {
    return cached;
  }
  const meta = typeof document !== "undefined"
    ? document.querySelector(`meta[name="${HEADER}"]`)
    : null;
  cached = meta?.getAttribute("content") ?? "seed-token";
  return cached;
}

export function withToken(headers: Record<string, string>): Record<string, string> {
  return { ...headers, [HEADER]: readToken() };
}

export function resetToken(): void {
  cached = null;
}
