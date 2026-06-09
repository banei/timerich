import type { BucketSignal, DateInfo } from "../../types/execution";
import ActionDateTag from "./ActionDateTag";

type Props = {
  signals: BucketSignal[];
  actionDate?: DateInfo;
};

function coefClass(coef: number) {
  if (coef < 1) return "text-warn";
  if (coef > 1) return "text-up";
  return "text-muted";
}

export default function SignalSummaryTable({ signals, actionDate }: Props) {
  if (!signals.length) return null;

  return (
    <div className="card exec-card">
      <div className="exec-header-row">
        <h3 className="exec-title">估值信号</h3>
        <ActionDateTag dateLabel={actionDate?.date_label} actionDate={actionDate?.date} />
      </div>
      <p className="deriv-note">月初首个交易日检查，确认本月系数后再分配金额。</p>
      <div className="signal-table">
        <div className="signal-row signal-head">
          <span>桶</span>
          <span>信号</span>
          <span>系数</span>
          <span>状态</span>
        </div>
        {signals.map((s) => (
          <div key={s.code} className="signal-row">
            <span className="signal-bucket">
              <i className="bucket-dot" style={{ background: s.color }} />
              {s.name}
            </span>
            <span className="font-num">{s.signal_display}</span>
            <span className={`font-num ${coefClass(s.coefficient)}`}>×{s.coefficient}</span>
            <span className="signal-badge" style={{ color: s.color }}>
              {s.coefficient_label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
