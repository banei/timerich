import type { BudgetReconciliation } from "../../types/execution";
import { fmtMoney } from "../../utils/formatNumber";

type Props = {
  reconciliation: BudgetReconciliation;
};

function fmtDelta(n: number) {
  if (Math.abs(n) < 0.01) return "±0";
  const sign = n > 0 ? "+" : "−";
  return `${sign}${fmtMoney(Math.abs(n))}`;
}

export default function BudgetReconciliationPanel({ reconciliation: r }: Props) {
  const showDetails = !r.aligned || r.has_manual_overrides || Math.abs(r.target_sum_pct - 1) > 0.001;

  return (
    <div className={`budget-recon ${r.aligned ? "budget-recon-ok" : "budget-recon-diff"}`}>
      <p className="budget-recon-lead">
        {r.aligned ? (
          <>
            计划合计与月预算<strong>一致</strong>（{fmtMoney(r.total_planned)}）。
            {r.spillover_moves.length > 0 && " 信号减速部分已在各桶间再分配。"}
          </>
        ) : (
          <>
            计划合计较月预算
            <strong className={r.delta > 0 ? "text-up" : "text-down"}>
              {r.delta > 0 ? "多" : "少"} {fmtMoney(Math.abs(r.delta))}
            </strong>
            （预算 {fmtMoney(r.budget)} → 计划 {fmtMoney(r.total_planned)}）。
          </>
        )}
      </p>

      <details className="budget-recon-details" open={showDetails}>
        <summary>推导过程</summary>
        <ol className="budget-recon-steps">
          {r.steps.map((step) => (
            <li key={step.key}>
              <span>{step.label}</span>
              <span className="font-num">{fmtMoney(step.amount)}</span>
              {step.delta_from_budget != null && Math.abs(step.delta_from_budget) >= 0.01 && (
                <span className="font-num text-muted">（较预算 {fmtDelta(step.delta_from_budget)}）</span>
              )}
            </li>
          ))}
        </ol>
        <ul className="budget-recon-notes">
          {r.summary_lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {r.override_adjustments.length > 0 && (
          <div className="budget-recon-overrides">
            <strong>手动调整</strong>
            <ul>
              {r.override_adjustments.map((a) => (
                <li key={a.bucket}>
                  {a.label}：{fmtMoney(a.from_amount)} → {fmtMoney(a.to_amount)}（{fmtDelta(a.delta)}）
                </li>
              ))}
            </ul>
          </div>
        )}
      </details>
    </div>
  );
}
