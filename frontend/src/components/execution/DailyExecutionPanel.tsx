import type { DailyBucketPlan, DailyExecutionContext } from "../../types/execution";
import ActionDateTag from "./ActionDateTag";
import DailyDcaBatchPanel from "./DailyDcaBatchPanel";
import FundFeeSummary from "./FundFeeSummary";
import GrowthLimitEditor from "./GrowthLimitEditor";

type Props = {
  daily: DailyExecutionContext;
  month: string;
  onReload: () => void;
  onRefreshNav?: () => void;
};

function fmt(n: number) {
  return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function ProgressBar({ invested, planned }: { invested: number; planned: number }) {
  const pct = planned > 0 ? Math.min(100, (invested / planned) * 100) : 0;
  return (
    <div className="daily-progress">
      <div className="daily-progress-bar" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function DailyExecutionPanel({ daily, month, onReload, onRefreshNav }: Props) {
  const g = daily.growth;
  const todayDone = g.today_invested >= g.today_target && g.today_target > 0;

  return (
    <div className="card exec-card daily-panel">
      <div className="exec-header-row">
        <h3 className="exec-title">今日定投 · 成长档（日维度）</h3>
        <ActionDateTag
          dateLabel={g.date_label || daily.date_label}
          actionDate={g.action_date || daily.date}
          recurrence="daily"
        />
      </div>

      {!daily.is_trading_day && daily.next_trading_date_label && (
        <p className="text-warn daily-hint">
          今日非交易日，请于 <strong>{daily.next_trading_date_label}</strong> 继续按剩余额度均摊。
        </p>
      )}

      <div className="daily-stats grid">
        <div className="stat daily-stat">
          <label>本月计划</label>
          <strong className="font-num">{fmt(g.monthly_planned)}</strong>
        </div>
        <div className="stat daily-stat">
          <label>已投入</label>
          <strong className="font-num">{fmt(g.monthly_invested)}</strong>
        </div>
        <div className="stat daily-stat">
          <label>月剩余</label>
          <strong className="font-num">{fmt(g.monthly_remaining)}</strong>
        </div>
        <div className="stat daily-stat">
          <label>今日目标</label>
          <strong className={`font-num ${todayDone ? "text-up" : ""}`}>{fmt(g.today_target)}</strong>
        </div>
        <div className="stat daily-stat">
          <label>今日已买</label>
          <strong className="font-num">{fmt(g.today_invested)}</strong>
        </div>
        <div className="stat daily-stat">
          <label>剩余交易日</label>
          <strong className="font-num">{daily.trading_days_remaining}</strong>
        </div>
      </div>

      <ProgressBar invested={g.monthly_invested} planned={g.monthly_planned} />
      <p className="daily-progress-label text-muted">
        本月进度 {daily.trading_days_elapsed}/{daily.trading_days_in_month} 个交易日
      </p>

      {g.execution_notes.map((note) => (
        <p key={note} className="deriv-note">{note}</p>
      ))}

      {daily.dca_batch && (
        <DailyDcaBatchPanel
          month={month}
          batch={daily.dca_batch}
          onReload={onReload}
          onRefreshNav={onRefreshNav}
        />
      )}

      {g.funds.length > 0 && (
        <>
          <div className="daily-limit-hint text-muted">
            {g.funds.map((f) => (
              <span key={f.fund_code} className="limit-chip">
                {f.fund_code}{" "}
                {f.purchase_status === "paused" ? "暂停" : f.daily_limit != null ? fmt(f.daily_limit) : "不限"}
              </span>
            ))}
          </div>
          <FundFeeSummary funds={g.funds} summary={g.fee_summary} label="今日申购费用" />
        </>
      )}

      {daily.growth_limits?.length > 0 && (
        <details className="daily-schedule growth-limit-details">
          <summary>纳指联接日限购设置（凑额度轮询顺序见上表）</summary>
          <GrowthLimitEditor month={month} limits={daily.growth_limits} onSaved={onReload} />
        </details>
      )}

      {daily.schedule.length > 0 && (
        <details className="daily-schedule">
          <summary>本月成长档日计划（按剩余额度均摊）</summary>
          <div className="schedule-table">
            {daily.schedule.map((row) => (
              <div
                key={row.date}
                className={`schedule-row ${row.is_today ? "schedule-today" : ""}`}
              >
                <span className="font-num">{row.date_label || row.date}</span>
                <span className="font-num">{fmt(row.target_amount)}</span>
                {row.is_today && <span className="badge">今日</span>}
              </div>
            ))}
          </div>
        </details>
      )}

      {daily.other_buckets.some((b) => b.monthly_planned > 0) && (
        <div className="monthly-buckets-hint">
          <h4 className="section-title">
            其他桶（月末/一次性）
            {daily.month_end_date_label && (
              <ActionDateTag dateLabel={daily.month_end_date_label} actionDate={daily.month_end_date} />
            )}
          </h4>
          <div className="other-bucket-list">
            {daily.other_buckets
              .filter((b) => b.monthly_planned > 0)
              .map((b) => (
                <div key={b.bucket} className="other-bucket-row">
                  <span className="signal-bucket">
                    <i className="bucket-dot" style={{ background: b.color }} />
                    {b.name}
                  </span>
                  <span className="font-num text-muted">
                    {fmt(b.monthly_invested)} / {fmt(b.monthly_planned)}
                  </span>
                  {b.date_label && <ActionDateTag dateLabel={b.date_label} actionDate={b.action_date} />}
                  {b.monthly_remaining > 0 && (
                    <span className="text-warn">待投 {fmt(b.monthly_remaining)}</span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
