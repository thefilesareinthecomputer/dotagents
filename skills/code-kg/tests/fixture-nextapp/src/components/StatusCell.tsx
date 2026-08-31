import { StatusPill } from "./StatusPill";
import type { InvoiceStatus } from "@/shared/types";

export function StatusCell({ status }: { status: InvoiceStatus }) {
  return (
    <td className="cell-status">
      <StatusPill status={status} />
    </td>
  );
}
