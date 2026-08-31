export type BadgeTone = "neutral" | "success" | "warning" | "danger";

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
