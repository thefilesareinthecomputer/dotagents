"use client";

import { Button } from "@/components";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="error-page">
      <h1>Something went wrong</h1>
      <p>{error.message}</p>
      <Button label="Try again" onClick={reset} />
    </main>
  );
}
