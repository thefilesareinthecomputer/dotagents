import { formatMoney } from "@/services/format";

export function MoneyCell({ amount, currency }: { amount: number; currency?: string }) {
  return <td className="cell-money">{formatMoney(amount, currency)}</td>;
}
