"use client";

import { useState } from "react";
import { TextField } from "./TextField";
import { Button } from "./Button";
import type { Customer } from "@/shared/types";

interface CustomerFormProps {
  initial?: Partial<Customer>;
  onSubmit: (input: Pick<Customer, "name" | "email">) => void;
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function CustomerForm({ initial, onSubmit }: CustomerFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [error, setError] = useState<string | null>(null);

  const submit = (event: { preventDefault: () => void }): void => {
    event.preventDefault();
    if (!EMAIL_RE.test(email)) {
      setError("Enter a valid email");
      return;
    }
    setError(null);
    onSubmit({ name, email });
  };

  return (
    <form className="customer-form" onSubmit={submit}>
      <TextField label="Name" name="name" value={name} onChange={setName} />
      <TextField
        label="Email"
        name="email"
        type="email"
        value={email}
        onChange={setEmail}
        error={error ?? undefined}
      />
      <Button label="Save customer" onClick={() => undefined} />
    </form>
  );
}
