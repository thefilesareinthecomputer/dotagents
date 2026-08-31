"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { currentUser, logout as logoutRequest } from "@/services/auth";
import type { User } from "@/shared/types";

interface UserContextValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const UserContext = createContext<UserContextValue | null>(null);

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async (): Promise<void> => {
    setLoading(true);
    const next = await currentUser();
    setUser(next);
    setLoading(false);
  };

  const signOut = async (): Promise<void> => {
    await logoutRequest();
    setUser(null);
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <UserContext.Provider value={{ user, loading, refresh, signOut }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) {
    throw new Error("useUser must be used within a UserProvider");
  }
  return ctx;
}
