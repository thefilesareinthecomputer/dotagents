"use client";

import { useState } from "react";
import { TextField } from "./TextField";
import { SelectField } from "./SelectField";
import { Button } from "./Button";
import { clampAmount } from "@/lib/currency";
import type { InvoiceDetail, InvoiceStatus } from "@/shared/types";

interface InvoiceFormProps {
  initial?: Partial<InvoiceDetail>;
  onSubmit: (draft: Partial<InvoiceDetail>) => void;
}

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "open", label: "Open" },
  { value: "paid", label: "Paid" },
];

export function InvoiceForm({ initial, onSubmit }: InvoiceFormProps) {
  const [number, setNumber] = useState(initial?.number ?? "");
  const [amount, setAmount] = useState(String(initial?.amount ?? ""));
  const [status, setStatus] = useState<InvoiceStatus>(initial?.status ?? "draft");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!number.trim()) {
      next.number = "Number is required";
    }
    if (Number.isNaN(Number(amount))) {
      next.amount = "Amount must be numeric";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = (event: { preventDefault: () => void }): void => {
    event.preventDefault();
    if (!validate()) {
      return;
    }
    onSubmit({
      number,
      amount: clampAmount(Number(amount)),
      status,
    });
  };

  return (
    <form className="invoice-form" onSubmit={submit}>
      <TextField label="Number" name="number" value={number} onChange={setNumber} error={errors.number} />
      <TextField label="Amount" name="amount" value={amount} onChange={setAmount} error={errors.amount} />
      <SelectField
        label="Status"
        name="status"
        value={status}
        options={STATUS_OPTIONS}
        onChange={(value) => setStatus(value as InvoiceStatus)}
      />
      <Button label="Save invoice" onClick={() => undefined} />
    </form>
  );
}
