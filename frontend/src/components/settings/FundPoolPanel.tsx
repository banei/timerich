import { FormEvent, useEffect, useState } from "react";
import { api } from "../../api";
import type { FundPoolItem } from "../../types/execution-v2";
import AmountQuickPicker from "../execution/v2/AmountQuickPicker";
import { FundConfigRow, saveFundPoolItem } from "../execution/v2/FundConfigRow";
import { FREQUENCY_OPTIONS } from "../execution/v2/fundConfigUtils";

type LookupResult = {
  fund_code: string;
  fund_name: string;
  purchase_limit: number | null;
};

export default function FundPoolPanel() {
  const [items, setItems] = useState<FundPoolItem[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState(10);
  const [frequency, setFrequency] = useState("daily");
  const [lookupMsg, setLookupMsg] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    const res = await api<FundPoolItem[]>("/api/v1/execution/fund-pool?bucket=growth");
    setItems(res.data || []);
  }

  useEffect(() => {
    load();
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
    if (!res.data) {
      setLookupMsg(res.error || "未找到");
      return;
    }
    setName(res.data.fund_name);
    setLookupMsg(res.data.fund_name);
  }

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    if (code.length !== 6) return;
    const err = await saveFundPoolItem({
      fund_code: code,
      fund_name: name,
      daily_limit: amount,
      frequency,
      sort_order: items.length,
    });
    if (err) {
      setMsg(err);
      return;
    }
    setCode("");
    setName("");
    setMsg("已添加");
    load();
  }

  async function remove(id: number) {
    await api(`/api/v1/execution/fund-pool/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>基金池 · 成长桶</h3>
      <p className="text-muted daily-hint">与定投页配置同步；输入代码自动查名称。</p>
      <div className="exec-v2-config-list">
        {items.map((item) => (
          <FundConfigRow key={item.id} item={item} showDelete onSaved={load} onDelete={remove} />
        ))}
      </div>
      <form className="exec-v2-add-fund" onSubmit={onAdd} style={{ marginTop: 12 }}>
        <div className="exec-v2-add-row">
          <input
            type="text"
            maxLength={6}
            placeholder="6位代码"
            value={code}
            onChange={(e) => lookupCode(e.target.value)}
          />
          <input type="text" placeholder="名称" value={name} readOnly />
          <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
            {FREQUENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <AmountQuickPicker value={amount} onChange={setAmount} />
        {lookupMsg && <p className="text-muted">{lookupMsg}</p>}
        <button type="submit" disabled={code.length !== 6}>
          添加基金
        </button>
        {msg && <span className="save-hint">{msg}</span>}
      </form>
    </div>
  );
}
