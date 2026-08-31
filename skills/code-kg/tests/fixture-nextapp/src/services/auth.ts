import { get, post } from "@/lib/http";
import { apiUrl } from "@/lib/env";
import { resetToken } from "@/services/csrf";
import type { Session, User } from "@/shared/types";

export interface Credentials {
  email: string;
  password: string;
}

export const login = async (creds: Credentials): Promise<Session> => {
  const session = await post<Session>(apiUrl("/auth/login"), creds);
  return session;
};

export const logout = async (): Promise<void> => {
  await post<void>(apiUrl("/auth/logout"), {});
  resetToken();
};

export const currentUser = async (): Promise<User | null> => {
  try {
    return await get<User>(apiUrl("/auth/me"));
  } catch {
    return null;
  }
};

export const hasRole = (user: User | null, role: User["role"]): boolean => {
  if (!user) {
    return false;
  }
  if (user.role === "admin") {
    return true;
  }
  return user.role === role;
};
