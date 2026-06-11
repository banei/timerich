import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { fmtMoney } from "../utils/formatNumber";
import ActionDateTag from "../components/execution/ActionDateTag";
import AmountDerivationTable from "../components/execution/AmountDerivationTable";
import BudgetReconciliationPanel from "../components/execution/BudgetReconciliationPanel";
import BucketExecutionCard from "../components/execution/BucketExecutionCard";
import DailyExecutionPanel from "../components/execution/DailyExecutionPanel";
import FundFeeSummary from "../components/execution/FundFeeSummary";
import SignalSummaryTable from "../components/execution/SignalSummaryTable";
import type { ActionStep, ExecutionPlan } from "../types/execution";

const STEP_TITLES: Record<string, string> = {
  check_signals: "Step 1 · 检查估值信号",
  calc_amounts: "Step 2 · 确认月金额分配",
  execute_nasdaq: "Step 3 · 成长档日定投",
  check_premium: "Step 4 · 检查 ETF 溢价",
  execute_dividend: "Step 5 · 执行红利档",
  execute_bond: "Step 6 · 执行债券档",
  record: "Step 7 · 录入交易记录",
};

export default function ExecutionLegacyPage() {
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [steps, setSteps] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState("0/7");

  const load = useCallback(async (opts?: { liveNav?: boolean }) => {
    const navQuery = opts?.liveNav ? "?live_nav=true" : "";
    const [planRes, monthRes] = await Promise.all([
      api<ExecutionPlan>(`/api/v1/execution/plan${navQuery}`),
      api<{ month: string; steps: Record<string, boolean>; progress: string }>(
        "/api/v1/execution/current-month",
      ),
    ]);
    if (planRes.data) setPlan(planRes.data);
    if (monthRes.data) {
      setSteps(monthRes.data.steps || {});
      setProgress(monthRes.data.progress || "0/7");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(step: string, completed: boolean) {
    if (!plan?.month) return;
    await api(`/api/v1/execution/${plan.month}/step/${step}`, {
      method: "PUT",
      body: JSON.stringify({ step_name: step, completed }),
    });
    load();
  }

  async function saveAmounts(amounts: Record<string, number>) {
    if (!plan?.month) return;
    await api(`/api/v1/execution/${plan.month}/amounts`, {
      method: "PUT",
      body: JSON.stringify({ amounts }),
    });
    load();
  }

  const actionSteps: ActionStep[] =
    plan?.action_steps ||
    Object.keys(STEP_TITLES).map((key) => ({
      key,
      title: STEP_TITLES[key],
      hint: "",
      recurrence: key === "execute_nasdaq" || key === "record" ? "daily" : "monthly",
      date: plan?.daily?.date || "",
      weekday: plan?.daily?.weekday || "",
      date_label: plan?.daily?.date_label || "",
    }));

  return (
    <>
      <div className="exec-summary card">
        <h2>{plan?.month || "—"} 定投执行</h2>
        <p>
          月预算 <span className="font-num">{fmtMoney(plan?.budget)}</span>
          {" · "}
          计划合计 <span className="font-num">{fmtMoney(plan?.total_planned)}</span>
          {" · "}
          清单进度 {progress}
        </p>
        {plan?.month_start && plan?.month_end && (
          <p className="exec-period text-muted">
            月初操作 <ActionDateTag dateLabel={plan.month_start.date_label} />
            {" · "}
            月末操作 <ActionDateTag dateLabel={plan.month_end.date_label} />
            {plan.daily?.date_label && (
              <>
                {" · "}
                今日 <ActionDateTag dateLabel={plan.daily.date_label} recurrence="daily" />
              </>
            )}
          </p>
        )}
        {plan?.budget_reconciliation && (
          <BudgetReconciliationPanel reconciliation={plan.budget_reconciliation} />
        )}
      </div>

      {plan?.daily && plan.month && (
        <DailyExecutionPanel
          daily={plan.daily}
          month={plan.month}
          onReload={() => load()}
          onRefreshNav={() => load({ liveNav: true })}
        />
      )}

      {plan && (
        <SignalSummaryTable signals={plan.signals} actionDate={plan.month_start} />
      )}
      {plan && (
        <AmountDerivationTable
          derivations={plan.derivations}
          onSave={saveAmounts}
          actionDate={plan.month_start}
        />
      )}

      {plan?.fee_summary && plan.bucket_executions.some((b) => b.funds.length > 0) && (
        <div className="card exec-card">
          <h3 className="exec-title">本月申购费用预估</h3>
          <FundFeeSummary
            funds={plan.bucket_executions.flatMap((b) => b.funds)}
            summary={plan.fee_summary}
            label="全月各桶合计"
          />
        </div>
      )}

      {plan && (
        <div className="bucket-grid">
          {plan.bucket_executions
            .filter((b) => b.bucket !== "growth")
            .map((b) => (
              <BucketExecutionCard key={b.bucket} bucket={b} />
            ))}
        </div>
      )}

      <div className="card exec-card">
        <h3 className="exec-title">执行清单</h3>
        <ul className="step-list">
          {actionSteps.map((step) => (
            <li key={step.key}>
              <label className="step-item">
                <input
                  type="checkbox"
                  checked={Boolean(steps[step.key])}
                  onChange={(e) => toggle(step.key, e.target.checked)}
                />
                <span className="step-content">
                  <span className="step-label">
                    {STEP_TITLES[step.key] || step.title}
                    <ActionDateTag
                      dateLabel={step.date_label}
                      actionDate={step.date}
                      recurrence={step.recurrence}
                    />
                  </span>
                  {step.hint && <span className="step-hint text-muted">{step.hint}</span>}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
