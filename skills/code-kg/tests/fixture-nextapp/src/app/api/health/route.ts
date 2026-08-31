import { checkToken } from "@/services/csrf";

export async function GET() {
  const ok = checkToken("health");
  return Response.json({ status: ok ? "ok" : "degraded" });
}
