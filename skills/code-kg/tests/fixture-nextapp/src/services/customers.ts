import { get, post, patch } from "@/lib/http";
import { apiUrl } from "@/lib/env";
import type { Customer, CustomerDetail, Page } from "@/shared/types";

export const listCustomers = async (query = ""): Promise<Page<Customer>> => {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return get<Page<Customer>>(apiUrl(`/customers${suffix}`));
};

export const getCustomer = async (id: string): Promise<CustomerDetail> => {
  return get<CustomerDetail>(apiUrl(`/customers/${id}`));
};

export const createCustomer = async (
  input: Pick<Customer, "name" | "email">,
): Promise<Customer> => {
  return post<Customer>(apiUrl("/customers"), input);
};

export const updateCustomer = async (
  id: string,
  input: Partial<Customer>,
): Promise<Customer> => {
  return patch<Customer>(apiUrl(`/customers/${id}`), input);
};
