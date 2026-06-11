import { useState } from "react";
import type { DateInfo, DerivationLine } from "../../types/execution";
import { fmtMoney } from "../../utils/formatNumber";
import ActionDateTag from "./ActionDateTag";

type Props = {
  derivations: DerivationLine[];
  onSave?: (amounts: Record<string, number>) => Promise<void>;
  actionDate?: DateInfo;
};

export default function AmountDerivationTable({ derivations, onSave, actionDate }: Props) {
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!onSave) return;
    const amounts: Record<string, number> = {};
    for (const [bucket, raw] of Object.entries(editing)) {
      const v = Number(raw);
      if (!Number.isNaN(v) && v >= 0) amounts[bucket] = v;
    }
    setSaving(true);
    try {
      await onSave(amounts);
      setEditing({});
    } finally {
      setSaving(false);
    }
  }

  const hasEdits = Object.keys(editing).length > 0;

  return (
    <div className="card exec-card">
      <div className="exec-header-row">
        <div>
          <h3 className="exec-title">金额推导</h3>
          <ActionDateTag dateLabel={actionDate?.date_label} actionDate={actionDate?.date} />
        </div>
        {onSave && hasEdits && (
          <button type="button" onClick={handleSave} disabled={saving}>
            {saving ? "保存中…" : "保存调整"}
          </button>
        )}
      </div>
      <div className="deriv-table">
        <div className="deriv-row deriv-head">
          <span>桶</span>
          <span>基础</span>
          <span>系数后</span>
          <span>溢出入</span>
          <span>最终</span>
        </div>
        {derivations.map((d) => (
          <div key={d.bucket} className="deriv-row">
            <span>{d.label}</span>
            <span className="font-num">{fmtMoney(d.base_amount)}</span>
            <span className="font-num">{fmtMoney(d.after_coefficient)}</span>
            <span className="font-num text-up">{d.spillover_in > 0 ? `+${fmtMoney(d.spillover_in)}` : "—"}</span>
            <span className="font-num">
              {d.editable && onSave ? (
                <input
                  className="deriv-input"
                  type="number"
                  min={0}
                  value={editing[d.bucket] ?? String(d.final_amount)}
                  onChange={(e) => setEditing({ ...editing, [d.bucket]: e.target.value })}
                />
              ) : (
                fmtMoney(d.final_amount)
              )}
            </span>
          </div>
        ))}
      </div>
      {derivations.map((d) =>
        d.notes ? (
          <p key={`${d.bucket}-note`} className="deriv-note">
            {d.label}：{d.notes}
          </p>
        ) : null,
      )}
    </div>
  );
}
