import { describe, it, expect } from "vitest";
import { toCents, fromCents, clampAmount, sumAmounts } from "./currency";

describe("currency", () => {
  it("round trips cents", () => {
    expect(toCents(9.5)).toBe(950);
    expect(fromCents(950)).toBe(9.5);
  });

  it("clamps out of range amounts", () => {
    expect(clampAmount(-5)).toBe(0);
    expect(clampAmount(5)).toBe(5);
    expect(clampAmount(Number.NaN)).toBe(0);
  });

  it("sums a list", () => {
    expect(sumAmounts([1, 2, 3])).toBe(6);
    expect(sumAmounts([])).toBe(0);
  });
});
