import { allCustomers } from "@/lib/repository";
import { truncate } from "@/services/format";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const q = url.searchParams.get("q")?.toLowerCase() ?? "";
  let items = allCustomers();
  if (q) {
    items = items.filter((c) => c.name.toLowerCase().includes(truncate(q, 60)));
  }
  return Response.json({ items, total: items.length, page: 1, pageSize: items.length });
}
