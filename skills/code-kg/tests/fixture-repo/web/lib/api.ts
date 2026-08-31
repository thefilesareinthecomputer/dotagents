import type { Zone } from "../models";

export const fetchZones = async (): Promise<Zone[]> => {
  const res = await fetch("/api/zones");
  return res.json();
};

export class ApiClient {
  base = "/api";
}
