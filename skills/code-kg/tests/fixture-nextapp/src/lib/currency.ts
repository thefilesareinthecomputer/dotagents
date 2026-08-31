const CENTS = 100;

export const toCents = (amount: number): number => {
  return Math.round(amount * CENTS);
};

export const fromCents = (cents: number): number => {
  return cents / CENTS;
};

export const clampAmount = (amount: number, min = 0, max = 1_000_000): number => {
  if (Number.isNaN(amount)) {
    return min;
  }
  return Math.min(Math.max(amount, min), max);
};

export const sumAmounts = (values: number[]): number => {
  return values.reduce((acc, v) => acc + v, 0);
};
