import type { FeeSummary, FundAllocation } from "../../types/execution";

type Props = {
  funds: FundAllocation[];
  summary?: FeeSummary | null;
  label?: string;
};

function fmtMoney(n: number) {
  return `¥${n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(rate: number) {
  return `${(rate * 100).toFixed(2)}%`;
}

export function FundFeeTable({ funds }: { funds: FundAllocation[] }) {
  if (!funds.length) return null;
  return (
    <table className="bucket-fund-table fund-fee-table">
      <thead>
        <tr>
          <th>基金</th>
          <th>申购金额</th>
          <th>申购费率</th>
          <th>申购费</th>
          <th>计入份额</th>
          <th>管理费/年</th>
        </tr>
      </thead>
      <tbody>
        {funds.map((f) => (
          <tr key={f.fund_code}>
            <td>
              <span className="font-num">{f.fund_code}</span> {f.fund_name}
            </td>
            <td className="font-num">{fmtMoney(f.planned_amount)}</td>
            <td className="font-num text-muted">
              {f.purchase_fee_rate != null ? fmtPct(f.purchase_fee_rate) : "—"}
            </td>
            <td className="font-num text-warn">
              {f.purchase_fee_amount != null ? fmtMoney(f.purchase_fee_amount) : "—"}
            </td>
            <td className="font-num text-up">
              {f.net_invested_amount != null ? fmtMoney(f.net_invested_amount) : "—"}
            </td>
            <td className="font-num text-muted">
              {f.annual_fee_rate != null ? fmtPct(f.annual_fee_rate) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function FundFeeSummary({ funds, summary, label = "费用合计" }: Props) {
  if (!funds.length) return null;
  const s =
    summary ||
    ({
      total_planned: funds.reduce((a, f) => a + f.planned_amount, 0),
      total_purchase_fee: funds.reduce((a, f) => a + (f.purchase_fee_amount || 0), 0),
      total_net_invested: funds.reduce((a, f) => a + (f.net_invested_amount || f.planned_amount), 0),
    } satisfies FeeSummary);

  return (
    <div className="fund-fee-summary">
      <FundFeeTable funds={funds} />
      <div className="fee-summary-row">
        <span className="text-muted">{label}</span>
        <span>
          申购 <span className="font-num">{fmtMoney(s.total_planned)}</span>
        </span>
        <span>
          申购费 <span className="font-num text-warn">{fmtMoney(s.total_purchase_fee)}</span>
        </span>
        <span>
          净投入 <span className="font-num text-up">{fmtMoney(s.total_net_invested)}</span>
        </span>
      </div>
      <p className="deriv-note">申购费按外扣估算；管理费为年化持有成本，不从申购金额扣减。</p>
    </div>
  );
}
