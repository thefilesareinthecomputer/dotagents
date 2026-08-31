"use client";

import { useEffect, useState } from "react";
import { fetchInvoices, createInvoice } from "@/services/api";
import { Button, Modal, InvoiceForm, EmptyState } from "@/components";
import { usePagination } from "@/hooks/usePagination";
import { formatMoney } from "@/services/format";
import type { Invoice, InvoiceDetail } from "@/shared/types";

export default function InvoicesPage() {
  const [rows, setRows] = useState<Invoice[]>([]);
  const [sortKey, setSortKey] = useState<string>("id");
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const pager = usePagination(rows.length);

  const handleLoad = async () => {
    const invoices = await fetchInvoices();
    setRows(invoices);
    setSelected(null);
  };

  const handleSort = (key: string) => {
    const next = [...rows];
    next.sort((a, b) => (a[key] > b[key] ? 1 : -1));
    setRows(next);
    setSortKey(key);
  };

  const handleSelect = (id: string) => {
    setSelected(id);
    const found = rows.find((r) => r.id === id);
    return found ?? null;
  };

  const handleClear = () => {
    setSelected(null);
    setSortKey("id");
    setRows([]);
  };

  const handleTotal = () => {
    let total = 0;
    for (const row of rows) {
      total += row.amount;
    }
    return total;
  };

  const handleCreate = async (draft: Partial<InvoiceDetail>) => {
    await createInvoice(draft);
    setCreating(false);
    await handleLoad();
  };

  useEffect(() => {
    void handleLoad();
  }, []);

  const total = handleTotal();

  return (
    <main>
      <h1>Invoices ({rows.length})</h1>
      <p>Sorted by {sortKey}</p>
      <p>Total: {formatMoney(total)}</p>
      <p>Selected: {selected ?? "none"}</p>
      <p>
        Page {pager.page} of {pager.totalPages}
      </p>
      <Button label="Load" onClick={() => void handleLoad()} />
      <Button label="Sort by amount" onClick={() => handleSort("amount")} />
      <Button label="New" onClick={() => setCreating(true)} />
      <Button label="Clear" onClick={handleClear} />
      {rows.length === 0 ? (
        <EmptyState title="No invoices" actionLabel="Load" onAction={() => void handleLoad()} />
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.id} onClick={() => handleSelect(row.id)}>
              <a href={`/invoices/${row.id}`}>{row.id}</a>: {formatMoney(row.amount)}
            </li>
          ))}
        </ul>
      )}
      <Modal open={creating} title="New invoice" onClose={() => setCreating(false)}>
        <InvoiceForm onSubmit={(draft) => void handleCreate(draft)} />
      </Modal>
    </main>
  );
}
