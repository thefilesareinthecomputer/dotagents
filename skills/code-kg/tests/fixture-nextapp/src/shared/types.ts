export interface Invoice {
  id: string;
  amount: number;
  [key: string]: string | number;
}

export type InvoiceStatus = "draft" | "open" | "paid" | "void" | "overdue";

export interface InvoiceDetail {
  id: string;
  number: string;
  customerId: string;
  amount: number;
  currency: string;
  status: InvoiceStatus;
  issuedAt: string;
  dueAt: string;
  lines: InvoiceLine[];
}

export interface InvoiceLine {
  id: string;
  description: string;
  quantity: number;
  unitAmount: number;
}

export interface Customer {
  id: string;
  name: string;
  email: string;
  createdAt: string;
  balance: number;
}

export interface CustomerDetail extends Customer {
  address: string;
  invoices: Invoice[];
  notes: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "member" | "viewer";
}

export interface Session {
  token: string;
  user: User;
  expiresAt: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface Settings {
  companyName: string;
  currency: string;
  invoicePrefix: string;
  emailReminders: boolean;
}
