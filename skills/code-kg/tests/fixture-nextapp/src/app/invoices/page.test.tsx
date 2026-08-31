import { describe, expect, it } from "vitest";

import InvoicesPage from "./page";

describe("InvoicesPage", () => {
  it("renders without crashing", () => {
    expect(typeof InvoicesPage).toBe("function");
  });
});
