import { fetchZones } from "./lib/api";
import { Zone } from "@app/models";

export async function renderDashboard(): Promise<Zone[]> {
  const zones = await fetchZones();
  return zones;
}
