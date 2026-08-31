import { greet } from "@/lib/util";
import { env } from "@/lib/env";

export default function HomePage() {
  return (
    <main>
      <h1>{greet(env.appName)}</h1>
      <p>Welcome to the invoicing workspace.</p>
      <ul>
        <li>
          <a href="/dashboard">Dashboard</a>
        </li>
        <li>
          <a href="/invoices">Invoices</a>
        </li>
        <li>
          <a href="/customers">Customers</a>
        </li>
      </ul>
    </main>
  );
}
