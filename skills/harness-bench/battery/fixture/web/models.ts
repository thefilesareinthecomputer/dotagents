export interface Zone {
  name: string;
  flow: number;
}

export type ZoneMap = Record<string, Zone>;
