import { Badge } from "./Badge";
import type { BadgeTone } from "./Badge";
import { formatStatus } from "@/services/format";
import type { InvoiceStatus } from "@/shared/types";

const TONES: Record<InvoiceStatus, BadgeTone> = {
  draft: "neutral",
  open: "neutral",
  paid: "success",
  void: "warning",
  overdue: "danger",
};

export function StatusPill({ status }: { status: InvoiceStatus }) {
  return <Badge tone={TONES[status]}>{formatStatus(status)}</Badge>;
}
