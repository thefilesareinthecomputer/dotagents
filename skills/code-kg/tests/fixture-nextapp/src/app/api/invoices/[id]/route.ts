import { invoiceById } from "@/lib/repository";

export async function GET(_request: Request, { params }: { params: { id: string } }) {
  const invoice = invoiceById(params.id);
  if (!invoice) {
    return Response.json({ error: "not found" }, { status: 404 });
  }
  return Response.json(invoice);
}
