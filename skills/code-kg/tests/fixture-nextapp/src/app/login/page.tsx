"use client";

import { LoginForm } from "@/components";
import { useUser } from "@/contexts/UserContext";

export default function LoginPage() {
  const { refresh } = useUser();

  const handleSuccess = (): void => {
    void refresh();
  };

  return (
    <main className="login-page">
      <h1>Sign in</h1>
      <LoginForm onSuccess={handleSuccess} />
    </main>
  );
}
