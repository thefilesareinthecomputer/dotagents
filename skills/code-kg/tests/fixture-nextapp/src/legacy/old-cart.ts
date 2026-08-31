export function computeCart(items: number[]): number {
  return items.reduce((sum, n) => sum + n, 0);
}
