import { defaultSettings } from "@/services/settings";

export async function GET() {
  return Response.json(defaultSettings());
}

export async function PATCH(request: Request) {
  const next = await request.json();
  return Response.json({ ...defaultSettings(), ...next });
}
