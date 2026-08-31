import { get, patch } from "@/lib/http";
import { apiUrl } from "@/lib/env";
import type { Settings } from "@/shared/types";

const DEFAULTS: Settings = {
  companyName: "Fixture Invoicing",
  currency: "USD",
  invoicePrefix: "INV",
  emailReminders: true,
};

export const loadSettings = async (): Promise<Settings> => {
  try {
    return await get<Settings>(apiUrl("/settings"));
  } catch {
    return { ...DEFAULTS };
  }
};

export const saveSettings = async (next: Settings): Promise<Settings> => {
  return patch<Settings>(apiUrl("/settings"), next);
};

export const defaultSettings = (): Settings => {
  return { ...DEFAULTS };
};
