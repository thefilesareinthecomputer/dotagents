"use client";

import { useState } from "react";
import { useAsync } from "@/hooks/useAsync";
import { useToggle } from "@/hooks/useToggle";
import { getCustomer, updateCustomer } from "@/services/customers";
import { Modal, CustomerForm, Spinner, EmptyState, Button } from "@/components";
import { formatMoney, formatDate } from "@/services/format";
import type { Customer } from "@/shared/types";

export default function CustomerDetailPage({ params }: { params: { id: string } }) {
  const { data, loading, reload } = useAsync(() => getCustomer(params.id), [params.id]);
  const [editing, toggleEditing] = useToggle(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = async (input: Pick<Customer, "name" | "email">): Promise<void> => {
    try {
      await updateCustomer(params.id, input);
      toggleEditing();
      reload();
    } catch {
      setSaveError("Could not save customer");
    }
  };

  if (loading) {
    return <Spinner label="Loading customer" />;
  }
  if (!data) {
    return <EmptyState title="Customer not found" />;
  }

  return (
    <main>
      <h1>{data.name}</h1>
      <p>{data.email}</p>
      <p>Balance: {formatMoney(data.balance)}</p>
      <p>Joined: {formatDate(data.createdAt)}</p>
      <p>{data.notes}</p>
      <Button label="Edit" onClick={toggleEditing} />
      {saveError ? <p className="form-error">{saveError}</p> : null}
      <Modal open={editing} title="Edit customer" onClose={toggleEditing}>
        <CustomerForm initial={data} onSubmit={(input) => void handleSave(input)} />
      </Modal>
    </main>
  );
}
