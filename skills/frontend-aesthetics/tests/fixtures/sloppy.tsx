// Fixture: deliberately full of tells. Every line here should trip a rule.
// Used by tests/test_slop_check.py. Do not "fix" this file.
import { ArrowRight } from "lucide-react";

export function Hero() {
  return (
    <section className="h-screen flex items-center justify-center bg-[#f5f1ea]">
      <div className="text-[11px] uppercase tracking-[0.18em]">01 / INDEX</div>
      <h1 style={{ fontFamily: "Inter, sans-serif", color: "#000000" }}>
        Elevate your workflow — seamlessly.
      </h1>
      <p>Trusted by Acme and John Doe · Lisbon · 14:23 · 18°C</p>
      <p>99.99% uptime 🚀</p>
      <span>Scroll to explore</span>
      <input placeholder="Email" />
      {/* ... */}
    </section>
  );
}
