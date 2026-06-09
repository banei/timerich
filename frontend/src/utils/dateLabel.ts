const WEEKDAY_ZH = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"] as const;

/** 将 ISO 日期格式化为「M月D日 周X」 */
export function formatDateWithWeekday(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getMonth() + 1}月${d.getDate()}日 ${WEEKDAY_ZH[d.getDay()]}`;
}

export function actionDateBadge(label?: string | null, fallbackIso?: string | null): string {
  if (label) return label;
  if (fallbackIso) return formatDateWithWeekday(fallbackIso);
  return "—";
}
