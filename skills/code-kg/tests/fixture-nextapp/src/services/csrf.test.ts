import { describe, it, expect, beforeEach } from "vitest";
import { checkToken, readToken, withToken, resetToken } from "./csrf";

describe("csrf", () => {
  beforeEach(() => {
    resetToken();
  });

  it("checks non-empty tokens", () => {
    expect(checkToken("abc")).toBe(true);
    expect(checkToken("")).toBe(false);
  });

  it("reads a seed token by default", () => {
    expect(readToken()).toBe("seed-token");
  });

  it("attaches the token header", () => {
    const headers = withToken({ accept: "application/json" });
    expect(headers["x-csrf-token"]).toBe("seed-token");
    expect(headers.accept).toBe("application/json");
  });
});
