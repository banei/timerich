import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import FundPoolPanel from "../components/settings/FundPoolPanel";

type BucketItem = {
  code: string;
  name: string;
  target_pct: number;
  color?: string;
};

type Config = {
  risk_profile: string;
  monthly_budget: number;
  bucket_config?: { buckets: BucketItem[] };
};

const BUCKET_HINT: Record<string, string> = {
  growth: "成长 / 纳指等权益",
  dividend: "红利低波",
  gold: "黄金",
  bond_long: "长期债券",
  bond_short: "短债 / 货基",
};

function SettingsForm() {
  const [config, setConfig] = useState<Config | null>(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Config>("/api/v1/config").then((r) => setConfig(r.data || null));
  }, []);

  const pctSum = useMemo(() => {
    if (!config?.bucket_config?.buckets) return 0;
    return config.bucket_config.buckets.reduce((s, b) => s + Number(b.target_pct), 0);
  }, [config]);

  function updateBucket(index: number, patch: Partial<BucketItem>) {
    if (!config?.bucket_config) return;
    const buckets = config.bucket_config.buckets.map((b, i) =>
      i === index ? { ...b, ...patch } : b,
    );
    setConfig({ ...config, bucket_config: { buckets } });
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!config) return;
    setError("");
    if (Math.abs(pctSum - 1) > 0.02) {
      setError(`五桶比例合计应为 100%，当前 ${(pctSum * 100).toFixed(1)}%`);
      return;
    }
    await api("/api/v1/config", {
      method: "PUT",
      body: JSON.stringify({
        risk_profile: config.risk_profile,
        monthly_budget: config.monthly_budget,
        bucket_config: config.bucket_config,
      }),
    });
    setSaved("已保存");
    setTimeout(() => setSaved(""), 2000);
  }

  if (!config) return <div>加载中...</div>;

  return (
    <form className="card" onSubmit={save}>
      <h3>账户配置</h3>
      <p className="text-muted" style={{ marginBottom: 16 }}>
        五桶名称与比例用于月度计划推导；基金频率与限购见下方「基金池」。
      </p>

      <div className="form-row">
        <label>风险档位</label>
        <select
          value={config.risk_profile}
          onChange={(e) => setConfig({ ...config, risk_profile: e.target.value })}
        >
          <option value="aggressive">进攻</option>
          <option value="balanced">平衡</option>
          <option value="defensive">防御</option>
        </select>
      </div>

      <div className="form-row">
        <label>月预算（元）</label>
        <input
          type="number"
          value={Number(config.monthly_budget)}
          onChange={(e) => setConfig({ ...config, monthly_budget: Number(e.target.value) })}
        />
      </div>

      <h4 className="section-title">五桶配比</h4>
      <table className="settings-bucket-table">
        <thead>
          <tr>
            <th>桶名称（可改）</th>
            <th>目标 %</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {config.bucket_config?.buckets.map((b, i) => (
            <tr key={b.code}>
              <td>
                <input
                  type="text"
                  value={b.name}
                  maxLength={32}
                  onChange={(e) => updateBucket(i, { name: e.target.value })}
                />
              </td>
              <td>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={Number(b.target_pct)}
                  onChange={(e) => updateBucket(i, { target_pct: Number(e.target.value) })}
                />
              </td>
              <td className="text-muted">{BUCKET_HINT[b.code] || b.code}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-muted" style={{ marginTop: 8 }}>
        比例合计：<span className="font-num">{(pctSum * 100).toFixed(1)}%</span>
        {Math.abs(pctSum - 1) > 0.02 && <span className="text-warn">（需调整为 100%）</span>}
      </p>

      {error && <p className="text-down">{error}</p>}

      <button type="submit">保存</button>
      {saved && <span className="save-hint">{saved}</span>}
    </form>
  );
}

export default function SettingsPage() {
  return (
    <>
      <SettingsForm />
      <FundPoolPanel />
    </>
  );
}
