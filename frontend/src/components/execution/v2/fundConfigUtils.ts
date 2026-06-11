export const AMOUNT_PRESETS = [0, 10, 20, 50, 100, 200] as const;

export const WEEKDAY_LABELS: Record<string, string> = {
  MON: "一",
  TUE: "二",
  WED: "三",
  THU: "四",
  FRI: "五",
  SAT: "六",
  SUN: "日",
};

export function frequencyLabel(freq: string): string {
  if (freq === "daily") return "每日";
  if (freq === "manual") return "手动";
  if (freq.startsWith("weekly_")) {
    const key = freq.split("_")[1]?.toUpperCase() || "";
    return `每周${WEEKDAY_LABELS[key] || key}`;
  }
  if (freq.startsWith("monthly_")) {
    const day = freq.split("_")[1] || "";
    return `每月${day}日`;
  }
  return freq;
}

export function buildFrequencyOptions(): { value: string; label: string }[] {
  const opts: { value: string; label: string }[] = [
    { value: "daily", label: "每日" },
  ];
  for (const [key, label] of Object.entries(WEEKDAY_LABELS)) {
    opts.push({ value: `weekly_${key}`, label: `每周${label}` });
  }
  for (let d = 1; d <= 28; d += 1) {
    opts.push({ value: `monthly_${d}`, label: `每月${d}日` });
  }
  opts.push({ value: "manual", label: "手动（仅主动提交）" });
  return opts;
}

export const FREQUENCY_OPTIONS = buildFrequencyOptions();

const WEEKDAY_MAP: Record<string, number> = {
  MON: 0,
  TUE: 1,
  WED: 2,
  THU: 3,
  FRI: 4,
  SAT: 5,
  SUN: 6,
};

function pyWeekday(d: Date): number {
  return (d.getDay() + 6) % 7;
}

function isTradingDay(d: Date): boolean {
  return pyWeekday(d) < 5;
}

function nextTradingDayOnOrAfter(d: Date): Date {
  const cur = new Date(d);
  while (!isTradingDay(cur)) {
    cur.setDate(cur.getDate() + 1);
  }
  return cur;
}

function getEffectiveMonthlyDay(year: number, month: number, dayNum: number): Date {
  const last = new Date(year, month + 1, 0).getDate();
  const day = Math.min(dayNum, last);
  return nextTradingDayOnOrAfter(new Date(year, month, day));
}

function sameCalendarDate(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** 与后端 should_buy_today 一致：该日期是否为该频率的计划定投日 */
export function shouldBuyOnDate(frequency: string, isoDate: string): boolean {
  if (frequency === "manual") return false;
  if (frequency === "daily") return true;
  const d = new Date(`${isoDate}T12:00:00`);
  if (frequency.startsWith("weekly_")) {
    const key = frequency.split("_")[1]?.toUpperCase() || "";
    const target = WEEKDAY_MAP[key];
    if (target === undefined) return false;
    return pyWeekday(d) === target;
  }
  if (frequency.startsWith("monthly_")) {
    const dayNum = parseInt(frequency.split("_")[1] || "", 10);
    if (!dayNum) return false;
    const eff = getEffectiveMonthlyDay(d.getFullYear(), d.getMonth(), dayNum);
    return sameCalendarDate(eff, d);
  }
  return false;
}

/** 加载/切换频率时是否默认勾选复选框 */
export function isDefaultSelected(frequency: string, isoDate: string): boolean {
  if (frequency === "daily") return true;
  if (frequency === "manual") return false;
  return shouldBuyOnDate(frequency, isoDate);
}
