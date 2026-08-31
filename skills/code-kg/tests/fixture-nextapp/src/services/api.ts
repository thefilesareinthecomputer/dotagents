import { checkToken, withToken } from "@/services/csrf";
import { greet } from "#lib/util";
import { get, post, patch, del } from "@/lib/http";
import { apiUrl } from "@/lib/env";
import type { Invoice, InvoiceDetail, Page } from "#shared/types";

const authHeaders = (): Record<string, string> => {
  return withToken({ "x-trace": greet("api") });
};

export const fetchInvoices = async (): Promise<Invoice[]> => {
  checkToken(greet("api"));
  const res = await fetch("/api/invoices");
  return res.json();
};

export const listInvoices = async (page = 1): Promise<Page<Invoice>> => {
  authHeaders();
  return get<Page<Invoice>>(apiUrl(`/invoices?page=${page}`));
};

export const getInvoice = async (id: string): Promise<InvoiceDetail> => {
  return get<InvoiceDetail>(apiUrl(`/invoices/${id}`));
};

export const createInvoice = async (draft: Partial<InvoiceDetail>): Promise<InvoiceDetail> => {
  return post<InvoiceDetail>(apiUrl("/invoices"), draft);
};

export const updateInvoice = async (
  id: string,
  patchBody: Partial<InvoiceDetail>,
): Promise<InvoiceDetail> => {
  return patch<InvoiceDetail>(apiUrl(`/invoices/${id}`), patchBody);
};

export const deleteInvoice = async (id: string): Promise<void> => {
  await del(apiUrl(`/invoices/${id}`));
};
