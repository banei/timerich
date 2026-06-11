import { FormEvent, useState } from "react";
import { api } from "../../api";
import type { CustomGrowthFund } from "../../types/execution";
import { fmtMoney } from "../../utils/formatNumber";

type Props = {
  month: string;
  funds: CustomGrowthFund[];
  onSaved: () => void;
};

export default function CustomFundEditor({ month, funds, onSaved }: Props) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [dailyLimit, setDailyLimit] = useState("");
  const [tier, setTier] = useState("2");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    const trimmed = code.trim();
    if (!/^\d{6}$/.test(trimmed)) {
      setMsg("请输入 6 位基金代码");
      return;
    }
    setBusy(true);
    setMsg("");
    const body: Record<string, unknown> = {
      fund_code: trimmed,
      tier: Number(tier),
    };
    if (name.trim()) body.fund_name = name.trim();
    if (dailyLimit.trim()) body.daily_limit = Number(dailyLimit);

    const res = await api(`/api/v1/execution/${month}/custom-growth-funds`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    setCode("");
    setName("");
    setDailyLimit("");
    setMsg("已添加");
    onSaved();
  }

  async function onRemove(fundCode: string) {
    setBusy(true);
    setMsg("");
    const res = await api(`/api/v1/execution/${month}/custom-growth-funds/${fundCode}`, {
      method: "DELETE",
    });
    setBusy(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    onSaved();
  }

  return (
    <div className="custom-fund-editor">
      <p className="text-muted daily-hint">
        添加不在内置名单中的纳指/成长类联接，将并入轮询阶梯参与日定投凑额度。留空名称可自动从天天基金拉取。
      </p>
      <form className="custom-fund-form" onSubmit={onAdd}>
        <input
          type="text"
          inputMode="numeric"
          maxLength={6}
          placeholder="基金代码"
          className="deriv-input custom-fund-code"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        />
        <input
          type="text"
          placeholder="名称（可选）"
          className="deriv-input custom-fund-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          type="number"
          min={0}
          step={1}
          placeholder="日限购"
          className="deriv-input custom-fund-limit"
          value={dailyLimit}
          onChange={(e) => setDailyLimit(e.target.value)}
        />
        <select className="deriv-input custom-fund-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
          <option value="1">阶梯 1（优先）</option>
          <option value="2">阶梯 2</option>
          <option value="3">阶梯 3</option>
          <option value="4">阶梯 4（标普备胎档）</option>
        </select>
        <button type="submit" disabled={busy || code.length !== 6}>
          {busy ? "添加中…" : "添加基金"}
        </button>
      </form>
      {msg && <p className={msg.includes("已") ? "save-hint" : "text-down"}>{msg}</p>}

      {funds.length > 0 && (
        <ul className="custom-fund-list">
          {funds.map((f) => (
            <li key={f.fund_code} className="custom-fund-row">
              <span className="font-num">{f.fund_code}</span>
              <span>{f.fund_name}</span>
              <span className="text-muted">
                阶梯 {f.tier} · 日限 {fmtMoney(f.daily_limit)}
              </span>
              <button
                type="button"
                className="secondary limit-pause-btn"
                disabled={busy}
                onClick={() => onRemove(f.fund_code)}
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
