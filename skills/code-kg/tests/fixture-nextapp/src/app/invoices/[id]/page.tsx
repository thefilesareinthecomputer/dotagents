"use client";

import { useState } from "react";
import { useAsync } from "@/hooks/useAsync";
import { useToggle } from "@/hooks/useToggle";
import { getInvoice, updateInvoice, deleteInvoice } from "@/services/api";
import { Modal, InvoiceForm, StatusPill, Spinner, EmptyState, Button } from "@/components";
import { formatMoney, formatDate } from "@/services/format";
import { isOverdue } from "@/lib/dates";
import type { InvoiceDetail } from "@/shared/types";

export default function InvoiceDetailPage({ params }: { params: { id: string } }) {
  const { data, loading, reload } = useAsync(() => getInvoice(params.id), [params.id]);
  const [editing, toggleEditing] = useToggle(false);
  const [busy, setBusy] = useState(false);

  const handleUpdate = async (draft: Partial<InvoiceDetail>): Promise<void> => {
    setBusy(true);
    await updateInvoice(params.id, draft);
    toggleEditing();
    setBusy(false);
    reload();
  };

  const handleDelete = async (): Promise<void> => {
    setBusy(true);
    await deleteInvoice(params.id);
    setBusy(false);
  };

  if (loading) {
    return <Spinner label="Loading invoice" />;
  }
  if (!data) {
    return <EmptyState title="Invoice not found" />;
  }

  const overdue = isOverdue(data.dueAt);
  return (
    <main>
      <h1>Invoice {data.number}</h1>
      <StatusPill status={overdue ? "overdue" : data.status} />
      <p>Amount: {formatMoney(data.amount, data.currency)}</p>
      <p>Issued: {formatDate(data.issuedAt)}</p>
      <p>Due: {formatDate(data.dueAt)}</p>
      <ul>
        {data.lines.map((line) => (
          <li key={line.id}>
            {line.description} - {formatMoney(line.unitAmount * line.quantity)}
          </li>
        ))}
      </ul>
      <Button label="Edit" onClick={toggleEditing} />
      <Button label="Delete" onClick={() => void handleDelete()} />
      {busy ? <Spinner label="Working" /> : null}
      <Modal open={editing} title="Edit invoice" onClose={toggleEditing}>
        <InvoiceForm initial={data} onSubmit={(draft) => void handleUpdate(draft)} />
      </Modal>
    </main>
  );
}
