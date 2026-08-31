import type { ReactNode } from "react";
import { UserProvider } from "@/contexts/UserContext";
import { Nav } from "@/components";
import { env } from "@/lib/env";
import "./globals.css";

export const metadata = {
  title: env.appName,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <UserProvider>
          <Nav />
          <div className="app-shell">{children}</div>
        </UserProvider>
      </body>
    </html>
  );
}
