import { describe, it, expect } from "vitest";
import { formatMoney, formatStatus, formatDate, truncate } from "./format";

describe("format", () => {
  it("formats money with a symbol", () => {
    expect(formatMoney(12.5)).toBe("$12.50");
    expect(formatMoney(5, "EUR")).toBe("EUR 5.00");
  });

  it("labels statuses", () => {
    expect(formatStatus("paid")).toBe("Paid");
    expect(formatStatus("overdue")).toBe("Overdue");
  });

  it("formats an ISO date", () => {
    expect(formatDate("2026-03-04T10:00:00Z")).toBe("2026-03-04");
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });

  it("truncates long text", () => {
    expect(truncate("abcdef", 4)).toBe("abc...");
    expect(truncate("abc", 4)).toBe("abc");
  });
});
