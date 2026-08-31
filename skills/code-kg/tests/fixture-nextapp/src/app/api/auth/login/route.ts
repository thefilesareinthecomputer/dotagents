import { checkToken } from "@/services/csrf";
import { greet } from "#lib/util";

export async function POST(request: Request) {
  const body = (await request.json()) as { email?: string };
  if (!checkToken(greet("login"))) {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }
  return Response.json({
    token: "seed-token",
    user: { id: "u1", name: body.email ?? "user", email: body.email ?? "", role: "member" },
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  });
}
