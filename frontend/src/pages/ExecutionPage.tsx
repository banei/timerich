import { useEffect, useState } from "react";
import { api } from "../api";

const STEPS = [
  ["check_signals", "Step 1 · 检查估值信号"],
  ["calc_amounts", "Step 2 · 确认金额分配"],
  ["execute_nasdaq", "Step 3 · 执行纳指档"],
  ["check_premium", "Step 4 · 检查 ETF 溢价"],
  ["execute_dividend", "Step 5 · 执行红利档"],
  ["execute_bond", "Step 6 · 执行债券档"],
  ["record", "Step 7 · 录入交易记录"],
];

export default function ExecutionPage() {
  const [data, setData] = useState<any>(null);

  async function load() {
    const res = await api("/api/v1/execution/current-month");
    setData(res.data);
  }

  useEffect(() => {
    load();
  }, []);

  async function toggle(step: string, completed: boolean) {
    if (!data?.month) return;
    await api(`/api/v1/execution/${data.month}/step/${step}`, {
      method: "PUT",
      body: JSON.stringify({ step_name: step, completed }),
    });
    load();
  }

  return (
    <div className="card">
      <h3>{data?.month || "—"} 定投执行清单</h3>
      <p>进度: {data?.progress || "0/7"}</p>
      <pre>{JSON.stringify(data?.planned, null, 2)}</pre>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {STEPS.map(([key, label]) => (
          <li key={key} style={{ marginBottom: 8 }}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(data?.steps?.[key])}
                onChange={(e) => toggle(key, e.target.checked)}
              />{" "}
              {label}
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
