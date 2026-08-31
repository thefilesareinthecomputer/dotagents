import { fromCents } from "@/lib/currency";
import type { InvoiceStatus } from "@/shared/types";

const STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Draft",
  open: "Open",
  paid: "Paid",
  void: "Void",
  overdue: "Overdue",
};

export const formatMoney = (amount: number, currency = "USD"): string => {
  const value = amount.toFixed(2);
  const symbol = currency === "USD" ? "$" : `${currency} `;
  return `${symbol}${value}`;
};

export const formatCents = (cents: number, currency = "USD"): string => {
  return formatMoney(fromCents(cents), currency);
};

export const formatStatus = (status: InvoiceStatus): string => {
  return STATUS_LABELS[status] ?? status;
};

export const formatDate = (iso: string): string => {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  return parsed.toISOString().slice(0, 10);
};

export const truncate = (text: string, max = 40): string => {
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
};
