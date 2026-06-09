import { useState } from "react";
import type { BucketExecution } from "../../types/execution";
import ActionDateTag from "./ActionDateTag";
import FundFeeSummary from "./FundFeeSummary";

type Props = {
  bucket: BucketExecution;
};

function fmt(n: number) {
  return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

export default function BucketExecutionCard({ bucket }: Props) {
  const [open, setOpen] = useState(bucket.total_amount > 0);

  return (
    <div className="card exec-card bucket-card" style={{ borderTopColor: bucket.color }}>
      <button type="button" className="bucket-card-header" onClick={() => setOpen(!open)}>
        <span className="bucket-header-main">
          <span className="signal-bucket">
            <i className="bucket-dot" style={{ background: bucket.color }} />
            {bucket.name}
          </span>
          <ActionDateTag dateLabel={bucket.date_label} actionDate={bucket.action_date} />
        </span>
        <span className="font-num">{fmt(bucket.total_amount)}</span>
        <span className="bucket-toggle">{open ? "收起" : "展开"}</span>
      </button>

      {open && (
        <div className="bucket-body">
          {bucket.funds.length === 0 ? (
            <p className="text-muted">本月无需执行</p>
          ) : (
            <FundFeeSummary
              funds={bucket.funds}
              summary={bucket.fee_summary}
              label={`${bucket.name} 申购费用`}
            />
          )}
          {bucket.execution_notes.map((note) => (
            <p key={note} className="deriv-note">
              {note}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
