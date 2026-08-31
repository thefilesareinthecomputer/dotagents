// Fixture: same component, tells removed. Must lint clean (zero findings).
// Used by tests/test_slop_check.py.
import { ArrowRight } from "@phosphor-icons/react";

export function Hero() {
  return (
    <section className="min-h-[100dvh] flex items-center bg-[#0f1211]">
      <h1 style={{ fontFamily: "Geist, sans-serif", color: "#fafaf9" }}>
        Ship the catalog, not the vibe.
      </h1>
      <p>463 entries. 9 added this week. 1 rejected.</p>
      <label htmlFor="email">Email</label>
      <input id="email" name="email" type="email" />
      <button type="submit">
        Start indexing <ArrowRight aria-hidden="true" />
      </button>
    </section>
  );
}
