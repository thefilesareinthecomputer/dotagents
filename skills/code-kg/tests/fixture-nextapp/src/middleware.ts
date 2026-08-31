import { checkToken } from "@/services/csrf";
import { apiUrl } from "@/lib/env";

const PROTECTED = ["/dashboard", "/invoices", "/customers", "/settings"];

export function middleware(request: Request) {
  const url = new URL(request.url);
  const needsAuth = PROTECTED.some((prefix) => url.pathname.startsWith(prefix));
  checkToken(request.url);
  if (needsAuth && !request.headers.get("cookie")) {
    return Response.redirect(new URL(apiUrl("/auth/login"), request.url));
  }
  return undefined;
}

export const config = {
  matcher: ["/dashboard/:path*", "/invoices/:path*", "/customers/:path*", "/settings/:path*"],
};
