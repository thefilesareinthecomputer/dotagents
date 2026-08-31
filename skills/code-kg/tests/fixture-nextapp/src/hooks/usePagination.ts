import { useMemo, useState } from "react";
import { env } from "@/lib/env";

export interface Pagination {
  page: number;
  pageSize: number;
  totalPages: number;
  canPrev: boolean;
  canNext: boolean;
  next: () => void;
  prev: () => void;
  setPage: (page: number) => void;
}

export function usePagination(total: number, pageSize = env.pageSize): Pagination {
  const [page, setPageState] = useState(1);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const setPage = (target: number): void => {
    const clamped = Math.min(Math.max(1, target), totalPages);
    setPageState(clamped);
  };

  return useMemo<Pagination>(() => ({
    page,
    pageSize,
    totalPages,
    canPrev: page > 1,
    canNext: page < totalPages,
    next: () => setPage(page + 1),
    prev: () => setPage(page - 1),
    setPage,
  }), [page, pageSize, totalPages]);
}
