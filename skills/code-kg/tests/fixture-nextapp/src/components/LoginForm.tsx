"use client";

import { useState } from "react";
import { TextField } from "./TextField";
import { Button } from "./Button";
import { Spinner } from "./Spinner";
import { login } from "@/services/auth";
import type { Credentials } from "@/services/auth";

interface LoginFormProps {
  onSuccess: () => void;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: { preventDefault: () => void }): Promise<void> => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const creds: Credentials = { email, password };
      await login(creds);
      onSuccess();
    } catch {
      setError("Invalid credentials");
    } finally {
      setPending(false);
    }
  };

  return (
    <form className="login-form" onSubmit={(e) => void submit(e)}>
      <TextField label="Email" name="email" type="email" value={email} onChange={setEmail} />
      <TextField label="Password" name="password" type="password" value={password} onChange={setPassword} />
      {error ? <p className="form-error">{error}</p> : null}
      {pending ? <Spinner label="Signing in" /> : <Button label="Sign in" onClick={() => undefined} />}
    </form>
  );
}
