"use client";

import { useUser } from "@/contexts/UserContext";
import { Button } from "./Button";

interface NavLink {
  href: string;
  label: string;
}

const LINKS: NavLink[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/invoices", label: "Invoices" },
  { href: "/customers", label: "Customers" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const { user, signOut } = useUser();

  return (
    <nav className="nav">
      <ul className="nav-links">
        {LINKS.map((link) => (
          <li key={link.href}>
            <a href={link.href}>{link.label}</a>
          </li>
        ))}
      </ul>
      <div className="nav-user">
        {user ? (
          <>
            <span>{user.name}</span>
            <Button label="Sign out" onClick={() => void signOut()} />
          </>
        ) : (
          <a href="/login">Sign in</a>
        )}
      </div>
    </nav>
  );
}
