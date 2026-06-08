import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";

export default function SettingsPage() {
  const [config, setConfig] = useState<any>(null);
  const [saved, setSaved] = useState("");

  useEffect(() => {
    api("/api/v1/config").then((r) => setConfig(r.data));
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    await api("/api/v1/config", { method: "PUT", body: JSON.stringify(config) });
    setSaved("已保存");
  }

  if (!config) return <div>加载中...</div>;

  return (
    <form className="card" onSubmit={save}>
      <h3>账户配置</h3>
      <div className="form-row">
        <label>风险档位</label>
        <select value={config.risk_profile} onChange={(e) => setConfig({ ...config, risk_profile: e.target.value })}>
          <option value="aggressive">进攻</option>
          <option value="balanced">平衡</option>
          <option value="defensive">防御</option>
        </select>
      </div>
      <div className="grid">
        <div className="form-row">
          <label>纳指目标 %</label>
          <input
            type="number"
            step="0.01"
            value={Number(config.target_nasdaq_pct)}
            onChange={(e) => setConfig({ ...config, target_nasdaq_pct: e.target.value })}
          />
        </div>
        <div className="form-row">
          <label>红利目标 %</label>
          <input
            type="number"
            step="0.01"
            value={Number(config.target_dividend_pct)}
            onChange={(e) => setConfig({ ...config, target_dividend_pct: e.target.value })}
          />
        </div>
        <div className="form-row">
          <label>债券目标 %</label>
          <input
            type="number"
            step="0.01"
            value={Number(config.target_bond_pct)}
            onChange={(e) => setConfig({ ...config, target_bond_pct: e.target.value })}
          />
        </div>
      </div>
      <div className="form-row">
        <label>月预算</label>
        <input
          type="number"
          value={Number(config.monthly_budget)}
          onChange={(e) => setConfig({ ...config, monthly_budget: e.target.value })}
        />
      </div>
      <button type="submit">保存</button>
      {saved && <span style={{ marginLeft: 8 }}>{saved}</span>}
    </form>
  );
}
