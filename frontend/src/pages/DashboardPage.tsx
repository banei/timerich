import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtMoney } from "../utils/formatNumber";

type AdviceBlock = {
  headline: string;
  actions: string[];
  tone?: string;
  priority?: string;
  recommendation?: string;
};

type AdviceData = {
  overall: AdviceBlock;
  nasdaq: AdviceBlock;
  dividend: AdviceBlock;
  spillover: AdviceBlock;
  allocation: AdviceBlock;
  amounts: { nasdaq: number; dividend: number; bond: number; total?: number };
};

type AllocationData = {
  current: Record<string, number>;
  target: Record<string, number>;
  deviations: Record<string, number>;
  advice?: AdviceBlock;
};

const TONE_CLASS: Record<string, string> = {
  aggressive: "advice-tone-aggressive",
  caution: "advice-tone-caution",
  neutral: "advice-tone-neutral",
};

const LABELS: Record<string, string> = {
  nasdaq: "纳指",
  dividend: "红利",
  bond: "债券",
};

function AdviceCard({ block }: { block: AdviceBlock }) {
  const toneClass = TONE_CLASS[block.tone || "neutral"] || TONE_CLASS.neutral;
  return (
    <div className={`advice-card ${toneClass}`}>
      <h4>{block.headline}</h4>
      <ul>
        {block.actions.map((action) => (
          <li key={action}>{action}</li>
        ))}
      </ul>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [signals, setSignals] = useState<Record<string, unknown> | null>(null);
  const [advice, setAdvice] = useState<AdviceData | null>(null);
  const [allocation, setAllocation] = useState<AllocationData | null>(null);

  useEffect(() => {
    api("/api/v1/dashboard/summary").then((r) => setSummary(r.data as Record<string, unknown>));
    api("/api/v1/dashboard/signals").then((r) => setSignals(r.data as Record<string, unknown>));
    api("/api/v1/dashboard/advice").then((r) => setAdvice(r.data as AdviceData));
    api("/api/v1/dashboard/allocation").then((r) => setAllocation(r.data as AllocationData));
  }, []);

  const overallTone = TONE_CLASS[advice?.overall?.priority || "neutral"] || TONE_CLASS.neutral;

  return (
    <>
      <div className="grid">
        <div className="stat">
          <label>总资产</label>
          <strong>{fmtMoney(summary?.total_value as number | string | undefined)}</strong>
        </div>
        <div className="stat">
          <label>累计浮盈</label>
          <strong>{fmtMoney(summary?.profit as number | string | undefined)}</strong>
        </div>
        <div className="stat">
          <label>浮盈率</label>
          <strong>{summary ? `${((summary.profit_rate as number) * 100).toFixed(1)}%` : "0%"}</strong>
        </div>
        <div className="stat">
          <label>家庭资产占比</label>
          <strong>
            {summary?.family_pct ? `${((summary.family_pct as number) * 100).toFixed(1)}%` : "—"}
          </strong>
        </div>
      </div>

      {advice?.overall && (
        <div className={`card advice-overall mt-16 ${overallTone}`}>
          <h3>操作建议</h3>
          <p className="advice-headline">{advice.overall.headline}</p>
          <ul className="advice-list">
            {advice.overall.actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="card mt-16">
        <h3>估值信号</h3>
        <div className="grid">
          <div>
            <strong>纳指100</strong>
            <p className="signal-meta">
              PE 分位: {signals ? (((signals.nasdaq as any).pe_percentile * 100).toFixed(0)) : "—"}% · 系数{" "}
              {(signals?.nasdaq as any)?.coefficient ?? "—"}（{(signals?.nasdaq as any)?.label}）
            </p>
            {(signals?.nasdaq as any)?.advice && (
              <AdviceCard block={(signals.nasdaq as any).advice} />
            )}
          </div>
          <div>
            <strong>红利低波</strong>
            <p className="signal-meta">
              股息率: {signals ? (((signals.dividend as any).dividend_yield * 100).toFixed(1)) : "—"}% · 系数{" "}
              {(signals?.dividend as any)?.coefficient ?? "—"}（{(signals?.dividend as any)?.label}）
            </p>
            {(signals?.dividend as any)?.advice && (
              <AdviceCard block={(signals.dividend as any).advice} />
            )}
          </div>
        </div>
      </div>

      {advice?.spillover && (
        <div className="card">
          <h3>定投执行</h3>
          <AdviceCard block={advice.spillover} />
          {advice.amounts && (
            <div className="amount-row">
              <span>纳指 {fmtMoney(advice.amounts.nasdaq)}</span>
              <span>红利 {fmtMoney(advice.amounts.dividend)}</span>
              <span>债券 {fmtMoney(advice.amounts.bond)}</span>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>配比偏离</h3>
        {allocation?.deviations && Object.keys(allocation.deviations).length > 0 ? (
          <>
            <table className="deviation-table">
              <thead>
                <tr>
                  <th>档位</th>
                  <th>当前</th>
                  <th>目标</th>
                  <th>偏离</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(allocation.target || {}).map((key) => (
                  <tr key={key}>
                    <td>{LABELS[key] || key}</td>
                    <td>{((allocation.current?.[key] || 0) * 100).toFixed(1)}%</td>
                    <td>{((allocation.target?.[key] || 0) * 100).toFixed(1)}%</td>
                    <td className={(allocation.deviations[key] || 0) < 0 ? "dev-negative" : "dev-positive"}>
                      {((allocation.deviations[key] || 0) * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {allocation.advice && <AdviceCard block={allocation.advice} />}
          </>
        ) : (
          <p className="signal-meta">暂无持仓，录入交易后将显示配比与再平衡建议。</p>
        )}
      </div>
    </>
  );
}
