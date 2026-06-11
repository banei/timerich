import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { fmtAmount, fmtMoney } from "../utils/formatNumber";

type Fund = { id: number; code: string; name: string };
type Holding = {
  fund_id: number;
  fund_code: string;
  fund_name: string;
  total_shares: string;
  total_invested: string;
  avg_cost?: string;
  current_nav?: string;
  current_value: string;
  profit_pct?: number;
  holding_days?: number;
  shares_over_one_year?: string;
  shares_under_one_year?: string;
};

export default function HoldingsPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    fund_id: "",
    txn_type: "buy",
    amount: "",
    nav: "",
    notes: "",
  });

  async function load() {
    const [h, f] = await Promise.all([
      api<Holding[]>("/api/v1/holdings"),
      api<Fund[]>("/api/v1/data/funds"),
    ]);
    setHoldings(h.data || []);
    setFunds(f.data || []);
  }

  useEffect(() => {
    load();
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    await api("/api/v1/transactions", {
      method: "POST",
      body: JSON.stringify({
        ...form,
        fund_id: Number(form.fund_id),
        amount: Number(form.amount),
        nav: Number(form.nav),
      }),
    });
    setShowForm(false);
    load();
  }

  return (
    <>
      <div className="page-actions">
        <button onClick={() => setShowForm(true)}>新增交易</button>
        <button className="secondary" style={{ marginLeft: 8 }} disabled>
          批量导入 CSV <span className="badge">待模板</span>
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>市值</th>
            <th>均价</th>
            <th>现价</th>
            <th>浮盈率</th>
            <th>持有超1年份额</th>
            <th>份额</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <tr key={h.fund_id}>
              <td>{h.fund_code}</td>
              <td>{h.fund_name}</td>
              <td className="font-num">{fmtMoney(h.current_value)}</td>
              <td className="font-num">{fmtAmount(h.avg_cost)}</td>
              <td className="font-num">{fmtAmount(h.current_nav)}</td>
              <td className={`font-num ${(h.profit_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                {h.profit_pct != null ? `${h.profit_pct >= 0 ? "+" : ""}${(h.profit_pct * 100).toFixed(1)}%` : "—"}
              </td>
              <td className="font-num" title="FIFO 统计，卖出时优先卖此部分（红利税 0%）">
                {h.shares_over_one_year ?? "0"}
              </td>
              <td className="font-num">{h.total_shares}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {showForm && (
        <div className="card">
          <h3>新增交易</h3>
          <form onSubmit={submit}>
            <div className="form-row">
              <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </div>
            <div className="form-row">
              <select value={form.fund_id} onChange={(e) => setForm({ ...form, fund_id: e.target.value })} required>
                <option value="">选择基金</option>
                {funds.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.code} {f.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <select value={form.txn_type} onChange={(e) => setForm({ ...form, txn_type: e.target.value })}>
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
                <option value="dividend">分红</option>
              </select>
            </div>
            <div className="form-row">
              <input
                placeholder="金额"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                required
              />
            </div>
            <div className="form-row">
              <input
                placeholder="净值"
                value={form.nav}
                onChange={(e) => setForm({ ...form, nav: e.target.value })}
                required
              />
            </div>
            <button type="submit">确认</button>
            <button type="button" className="secondary" style={{ marginLeft: 8 }} onClick={() => setShowForm(false)}>
              取消
            </button>
          </form>
        </div>
      )}
    </>
  );
}
