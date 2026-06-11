const AMOUNT_OPTS: Intl.NumberFormatOptions = {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
};

function toNum(n: number | string | null | undefined): number | null {
  if (n == null || n === "") return null;
  const num = typeof n === "string" ? Number(n) : n;
  return Number.isNaN(num) ? null : num;
}

/** 金额/净值数字，固定 2 位小数（无货币符号） */
export function fmtAmount(n: number | string | null | undefined): string {
  const num = toNum(n);
  if (num == null) return "—";
  return num.toLocaleString("zh-CN", AMOUNT_OPTS);
}

/** 带 ¥ 的金额，固定 2 位小数 */
export function fmtMoney(n: number | string | null | undefined): string {
  const s = fmtAmount(n);
  return s === "—" ? "—" : `¥${s}`;
}
