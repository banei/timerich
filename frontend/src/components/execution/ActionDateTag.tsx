import { actionDateBadge } from "../../utils/dateLabel";

type Props = {
  dateLabel?: string | null;
  actionDate?: string | null;
  recurrence?: "daily" | "monthly";
};

export default function ActionDateTag({ dateLabel, actionDate, recurrence }: Props) {
  const text = actionDateBadge(dateLabel, actionDate);
  if (text === "—") return null;
  return (
    <span className={`action-date-tag ${recurrence === "daily" ? "action-date-daily" : ""}`}>
      {recurrence === "daily" ? "每日 · " : "操作日 · "}
      {text}
    </span>
  );
}
