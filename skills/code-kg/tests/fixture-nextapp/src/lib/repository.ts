import { query, one, run } from "./db";
import { clampAmount } from "./currency";
import type { Invoice, InvoiceDetail, Customer } from "#shared/types";

export const allInvoices = (): Invoice[] => {
  return query<Invoice>("SELECT id, amount FROM invoices ORDER BY id");
};

export const invoiceById = (id: string): InvoiceDetail | undefined => {
  return one<InvoiceDetail>("SELECT * FROM invoices WHERE id = ?", [id]);
};

export const insertInvoice = (draft: Partial<InvoiceDetail>): void => {
  run("INSERT INTO invoices (id, amount) VALUES (?, ?)", [
    draft.id ?? "",
    clampAmount(draft.amount ?? 0),
  ]);
};

export const allCustomers = (): Customer[] => {
  return query<Customer>("SELECT id, name, email, balance FROM customers");
};

export const customerById = (id: string): Customer | undefined => {
  return one<Customer>("SELECT * FROM customers WHERE id = ?", [id]);
};
