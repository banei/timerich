import { FormEvent, useState } from "react";
import { api } from "../../api";
import type { GrowthLimitRow } from "../../types/execution";

type Props = {
  month: string;
  limits: GrowthLimitRow[];
  onSaved: () => void;
};

export default function GrowthLimitEditor({ month, limits, onSaved }: Props) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(limits.map((r) => [r.fund_code, String(r.daily_limit ?? 0)])),
  );
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    const payload: Record<string, number> = {};
    for (const [code, raw] of Object.entries(draft)) {
      payload[code] = Number(raw);
    }
    const res = await api(`/api/v1/execution/${month}/growth-limits`, {
      method: "PUT",
      body: JSON.stringify({ limits: payload }),
    });
    setSaving(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    setMsg("已保存");
    onSaved();
  }

  function setPaused(code: string) {
    setDraft((d) => ({ ...d, [code]: "0" }));
  }

  return (
    <form className="growth-limit-editor" onSubmit={onSubmit}>
      <p className="text-muted daily-hint">
        按 App 实际限额调整：0 = 暂停申购。当前可买名单见上方「纳指100候选名单」。
      </p>
      <div className="limit-editor-grid">
        {limits.map((row) => (
          <div key={row.fund_code} className="limit-editor-row">
            <span className="limit-fund-name">
              <span className="font-num">{row.fund_code}</span> {row.fund_name}
            </span>
            <input
              type="number"
              min={0}
              step={1}
              className="deriv-input"
              value={draft[row.fund_code] ?? "0"}
              onChange={(e) => setDraft((d) => ({ ...d, [row.fund_code]: e.target.value }))}
            />
            <button type="button" className="secondary limit-pause-btn" onClick={() => setPaused(row.fund_code)}>
              暂停
            </button>
            {row.status === "paused" && <span className="text-down limit-status">暂停中</span>}
          </div>
        ))}
      </div>
      <div className="limit-editor-actions">
        <button type="submit" disabled={saving}>
          {saving ? "保存中…" : "保存限购"}
        </button>
        {msg && <span className={msg === "已保存" ? "save-hint" : "text-down"}>{msg}</span>}
      </div>
    </form>
  );
}
