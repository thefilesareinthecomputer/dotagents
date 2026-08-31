const DAY_MS = 24 * 60 * 60 * 1000;

export const startOfDay = (input: Date): Date => {
  const copy = new Date(input.getTime());
  copy.setHours(0, 0, 0, 0);
  return copy;
};

export const addDays = (input: Date, days: number): Date => {
  return new Date(input.getTime() + days * DAY_MS);
};

export const daysBetween = (a: Date, b: Date): number => {
  const diff = startOfDay(b).getTime() - startOfDay(a).getTime();
  return Math.round(diff / DAY_MS);
};

export const isOverdue = (due: string, now: Date = new Date()): boolean => {
  const parsed = new Date(due);
  if (Number.isNaN(parsed.getTime())) {
    return false;
  }
  return parsed.getTime() < startOfDay(now).getTime();
};
