import { checkToken } from "@/services/csrf";
import { allInvoices, insertInvoice } from "@/lib/repository";
import type { InvoiceDetail } from "@/shared/types";

export async function GET() {
  const items = allInvoices();
  return Response.json({ items, total: items.length, page: 1, pageSize: items.length });
}

export async function POST(request: Request) {
  if (!checkToken(request.headers.get("x-csrf-token") ?? "")) {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }
  const draft = (await request.json()) as Partial<InvoiceDetail>;
  insertInvoice(draft);
  return Response.json({ ok: true }, { status: 201 });
}
