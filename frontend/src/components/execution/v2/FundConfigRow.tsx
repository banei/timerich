import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../../api";
import type { FundPoolItem } from "../../../types/execution-v2";
import AmountQuickPicker from "./AmountQuickPicker";
import { FREQUENCY_OPTIONS, frequencyLabel } from "./fundConfigUtils";

type SavePayload = Partial<FundPoolItem> & { fund_code: string; bucket_code?: string };

type Props = {
  item: FundPoolItem | SavePayload;
  dueToday?: boolean;
  showDelete?: boolean;
  onSaved: () => void;
  onDelete?: (id: number) => void;
};

export async function saveFundPoolItem(item: SavePayload): Promise<string | null> {
  const res = await api("/api/v1/execution/fund-pool", {
    method: "PUT",
    body: JSON.stringify({
      bucket_code: item.bucket_code || "growth",
      fund_code: item.fund_code,
      fund_name: item.fund_name,
      daily_limit: item.daily_limit ?? 10,
      frequency: item.frequency ?? "daily",
      buy_type: item.buy_type ?? "scheduled",
      status: item.status,
      sort_order: item.sort_order ?? 0,
    }),
  });
  return res.error || null;
}

export function FundConfigRow({ item, dueToday, showDelete, onSaved, onDelete }: Props) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [amount, setAmount] = useState(item.daily_limit ?? 0);
  const [frequency, setFrequency] = useState(item.frequency || "daily");

  useEffect(() => {
    setAmount(item.daily_limit ?? 0);
    setFrequency(item.frequency || "daily");
  }, [item.daily_limit, item.frequency, item.fund_code]);

  const persist = useCallback(
    (patch: Partial<FundPoolItem>) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(async () => {
        const err = await saveFundPoolItem({
          ...item,
          ...patch,
          fund_code: item.fund_code,
          bucket_code: item.bucket_code || "growth",
        });
        if (!err) onSaved();
      }, 400);
    },
    [item, onSaved],
  );

  const paused = item.status === "paused" || amount <= 0;

  return (
    <div className={`exec-v2-config-row ${paused ? "exec-v2-config-paused" : ""}`}>
      <div className="exec-v2-config-meta">
        {dueToday && <span className="exec-v2-today-badge">今日</span>}
        <span className="font-num exec-v2-code">{item.fund_code}</span>
        <span className="exec-v2-name" title={item.fund_name}>
          {item.fund_name}
        </span>
      </div>
      <div className="exec-v2-config-controls">
        <AmountQuickPicker
          compact
          value={amount}
          onChange={(n) => {
            setAmount(n);
            persist({
              daily_limit: n,
              status: n <= 0 ? "paused" : "active",
            });
          }}
        />
        <select
          className="exec-v2-freq-select"
          value={frequency}
          onChange={(e) => {
            setFrequency(e.target.value);
            persist({ frequency: e.target.value });
          }}
          title={frequencyLabel(frequency)}
        >
          {FREQUENCY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {showDelete && "id" in item && item.id > 0 && onDelete && (
          <button type="button" className="secondary exec-v2-mini-btn" onClick={() => onDelete(item.id)}>
            删除
          </button>
        )}
      </div>
    </div>
  );
}
