"use client";

import { useAsync } from "@/hooks/useAsync";
import { listInvoices } from "@/services/api";
import { formatMoney } from "@/services/format";
import { sumAmounts } from "@/lib/currency";
import { Spinner, EmptyState } from "@/components";
import type { Invoice } from "@/shared/types";
import "./dashboard.css";

interface Stat {
  label: string;
  value: string;
}

const buildStats = (invoices: Invoice[]): Stat[] => {
  const total = sumAmounts(invoices.map((i) => i.amount));
  return [
    { label: "Invoices", value: String(invoices.length) },
    { label: "Outstanding", value: formatMoney(total) },
    { label: "Average", value: formatMoney(invoices.length ? total / invoices.length : 0) },
  ];
};

export default function DashboardPage() {
  const { data, loading } = useAsync(() => listInvoices(1), []);

  if (loading) {
    return <Spinner label="Loading dashboard" />;
  }

  const invoices = data?.items ?? [];
  if (invoices.length === 0) {
    return <EmptyState title="No activity yet" description="Create an invoice to get started." />;
  }

  const stats = buildStats(invoices);
  return (
    <main>
      <h1>Dashboard</h1>
      <div className="dashboard-grid">
        {stats.map((stat) => (
          <div key={stat.label} className="stat-card">
            <div className="stat-value">{stat.value}</div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>
    </main>
  );
}
