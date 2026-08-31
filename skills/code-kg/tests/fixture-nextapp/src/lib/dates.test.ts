import { describe, it, expect } from "vitest";
import { addDays, daysBetween, isOverdue, startOfDay } from "./dates";

describe("dates", () => {
  it("adds days", () => {
    const base = new Date("2026-01-01T12:00:00Z");
    expect(addDays(base, 2).getUTCDate()).toBe(3);
  });

  it("counts days between", () => {
    const a = new Date("2026-01-01T00:00:00Z");
    const b = new Date("2026-01-05T00:00:00Z");
    expect(daysBetween(a, b)).toBe(4);
  });

  it("detects overdue", () => {
    const now = new Date("2026-06-01T00:00:00Z");
    expect(isOverdue("2026-05-01", now)).toBe(true);
    expect(isOverdue("2026-07-01", now)).toBe(false);
  });

  it("zeroes the clock", () => {
    const d = startOfDay(new Date("2026-01-01T18:30:00"));
    expect(d.getHours()).toBe(0);
  });
});
