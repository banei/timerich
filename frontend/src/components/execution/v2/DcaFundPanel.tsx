import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../../../api";
import type { FundPoolItem, TodayView } from "../../../types/execution-v2";
import { FundConfigRow, saveFundPoolItem } from "./FundConfigRow";
import AmountQuickPicker from "./AmountQuickPicker";
import { FREQUENCY_OPTIONS } from "./fundConfigUtils";

type Props = {
  today: TodayView | null;
  onReload: () => void;
};

type LookupResult = {
  fund_code: string;
  fund_name: string;
  purchase_limit: number | null;
};

export default function DcaFundPanel({ today, onReload }: Props) {
  const [items, setItems] = useState<FundPoolItem[]>([]);
  const [expanded, setExpanded] = useState(true);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState(10);
  const [frequency, setFrequency] = useState("daily");
  const [lookupMsg, setLookupMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const dueTodayCodes = useMemo(() => {
    const codes = new Set<string>();
    if (!today) return codes;
    for (const g of today.bucket_groups) {
      for (const f of g.funds || []) codes.add(f.fund_code);
    }
    return codes;
  }, [today]);

  async function loadPool() {
    const res = await api<FundPoolItem[]>("/api/v1/execution/fund-pool?bucket=growth");
    setItems(res.data || []);
  }

  useEffect(() => {
    loadPool();
  }, []);

  async function lookupCode(raw: string) {
    const trimmed = raw.replace(/\D/g, "").slice(0, 6);
    setCode(trimmed);
    if (trimmed.length !== 6) {
      setLookupMsg("");
      return;
    }
    setLookupMsg("查询中…");
    const res = await api<LookupResult>(`/api/v1/execution/fund-lookup?code=${trimmed}`);
    if (res.error || !res.data) {
      setLookupMsg(res.error || "未找到基金");
      return;
    }
    setName(res.data.fund_name);
    if (res.data.purchase_limit != null && res.data.purchase_limit > 0) {
      setAmount(Math.min(10, res.data.purchase_limit));
    }
    setLookupMsg(res.data.fund_name);
  }

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    if (code.length !== 6) {
      setMsg("请输入 6 位基金代码");
      return;
    }
    setBusy(true);
    setMsg("");
    const err = await saveFundPoolItem({
      fund_code: code,
      fund_name: name || code,
      daily_limit: amount,
      frequency,
      buy_type: "scheduled",
      status: amount <= 0 ? "paused" : "active",
      sort_order: items.length,
    });
    setBusy(false);
    if (err) {
      setMsg(err);
      return;
    }
    setCode("");
    setName("");
    setAmount(10);
    setLookupMsg("");
    setMsg("已添加");
    await loadPool();
    onReload();
  }

  async function onDelete(id: number) {
    await api(`/api/v1/execution/fund-pool/${id}`, { method: "DELETE" });
    await loadPool();
    onReload();
  }

  const scheduled = items.filter((i) => i.buy_type !== "probe");
  const probes = items.filter((i) => i.buy_type === "probe");

  return (
    <section className="card exec-v2-section exec-v2-fund-panel">
      <header className="exec-v2-header">
        <button type="button" className="exec-v2-summary" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "▼" : "▶"} 定投基金配置
        </button>
        <span className="text-muted">{scheduled.length} 只正式 · {probes.length} 只试探</span>
      </header>

      {expanded && (
        <>
          <p className="text-muted daily-hint">
            设置每只基金的定投金额与频率；金额为 0 或点「暂停」即暂停该基金。今日应买的基金会标「今日」。
          </p>

          <div className="exec-v2-config-list">
            {scheduled.map((item) => (
              <FundConfigRow
                key={item.id}
                item={item}
                dueToday={dueTodayCodes.has(item.fund_code)}
                showDelete
                onSaved={() => {
                  loadPool();
                  onReload();
                }}
                onDelete={onDelete}
              />
            ))}
          </div>

          {probes.length > 0 && (
            <>
              <h4 className="exec-v2-subhead">试探性买入</h4>
              <div className="exec-v2-config-list">
                {probes.map((item) => (
                  <FundConfigRow
                    key={item.id}
                    item={item}
                    dueToday={dueTodayCodes.has(item.fund_code)}
                    showDelete
                    onSaved={() => {
                      loadPool();
                      onReload();
                    }}
                    onDelete={onDelete}
                  />
                ))}
              </div>
            </>
          )}

          <form className="exec-v2-add-fund" onSubmit={onAdd}>
            <h4>添加基金</h4>
            <div className="exec-v2-add-row">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="6位代码"
                className="exec-v2-add-code font-num"
                value={code}
                onChange={(e) => lookupCode(e.target.value)}
              />
              <input
                type="text"
                placeholder="名称（自动填充）"
                className="exec-v2-add-name"
                value={name}
                readOnly
              />
              <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                {FREQUENCY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <AmountQuickPicker value={amount} onChange={setAmount} />
            {lookupMsg && <p className="text-muted exec-v2-lookup-hint">{lookupMsg}</p>}
            <button type="submit" disabled={busy || code.length !== 6} style={{ marginTop: 8 }}>
              {busy ? "添加中…" : "添加基金"}
            </button>
            {msg && <span className={msg.includes("已") ? "save-hint" : "text-down"}>{msg}</span>}
          </form>
        </>
      )}
    </section>
  );
}
