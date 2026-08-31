"use client";

import { useEffect, useState } from "react";
import { listCustomers } from "@/services/customers";
import { useDebounce } from "@/hooks/useDebounce";
import { usePagination } from "@/hooks/usePagination";
import { TextField, EmptyState, Spinner, Button } from "@/components";
import { formatMoney } from "@/services/format";
import type { Customer } from "@/shared/types";

export default function CustomersPage() {
  const [query, setQuery] = useState("");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const debounced = useDebounce(query, 250);
  const pager = usePagination(total);

  useEffect(() => {
    let active = true;
    setLoading(true);
    listCustomers(debounced)
      .then((res) => {
        if (active) {
          setCustomers(res.items);
          setTotal(res.total);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [debounced, pager.page]);

  return (
    <main>
      <h1>Customers</h1>
      <TextField label="Search" name="q" value={query} onChange={setQuery} placeholder="Filter by name" />
      {loading ? <Spinner /> : null}
      {!loading && customers.length === 0 ? (
        <EmptyState title="No customers found" />
      ) : (
        <table className="data-table">
          <tbody>
            {customers.map((customer) => (
              <tr key={customer.id}>
                <td>
                  <a href={`/customers/${customer.id}`}>{customer.name}</a>
                </td>
                <td>{customer.email}</td>
                <td>{formatMoney(customer.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="pager">
        <Button label="Prev" onClick={pager.prev} />
        <span>
          {pager.page} / {pager.totalPages}
        </span>
        <Button label="Next" onClick={pager.next} />
      </div>
    </main>
  );
}
